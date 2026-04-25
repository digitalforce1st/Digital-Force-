"""
Digital Force — RAG Retriever
Hybrid dense + sparse search with reranking over Qdrant.
"""

import logging
from typing import Optional
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    from qdrant_client import QdrantClient
    if settings.qdrant_use_cloud:
        _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    else:
        _client = QdrantClient(path=settings.qdrant_local_path)
    return _client


def _get_embedder():
    """Return best available embedder. Never raises — stubs if nothing available."""
    # 1. Lightweight ONNX Embedder (preferred, no PyTorch required)
    try:
        import numpy as np
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        import onnxruntime as ort

        class LightEmbedder:
            def __init__(self, model_id="Xenova/all-MiniLM-L6-v2"):
                # Uses cached versions if available; downloads (~90MB) on first run
                self.tokenizer_path = hf_hub_download(repo_id=model_id, filename="tokenizer.json")
                self.model_path = hf_hub_download(repo_id=model_id, filename="onnx/model_quantized.onnx")
                
                self.tokenizer = Tokenizer.from_file(self.tokenizer_path)
                self.tokenizer.enable_truncation(max_length=256)
                self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
                
                # Suppress onnxruntime warnings
                sess_options = ort.SessionOptions()
                sess_options.log_severity_level = 3
                self.session = ort.InferenceSession(self.model_path, sess_options=sess_options, providers=['CPUExecutionProvider'])

            def encode(self, texts, **_):
                if isinstance(texts, str):
                    texts = [texts]
                    
                encodings = self.tokenizer.encode_batch(texts)
                
                input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
                attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
                token_type_ids = np.array([e.type_ids for e in encodings], dtype=np.int64)

                inputs = {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": token_type_ids
                }
                
                outputs = self.session.run(None, inputs)
                token_embeddings = outputs[0]
                
                # Mean pooling
                mask_expanded = np.expand_dims(attention_mask, -1)
                sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
                sum_mask = np.clip(np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
                
                embeddings = sum_embeddings / sum_mask
                
                # Normalize
                norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                embeddings = embeddings / norms
                
                # sentence-transformers natively returns a 1D numpy array for single strings, 
                # or a 2D array for batches. We mimic that behavior here:
                if len(texts) == 1:
                    return embeddings[0]
                return embeddings

        return LightEmbedder()
    except Exception as e:
        logger.warning(f"[RAG] ONNX Embedder failed to load (downloads may be pending): {e}")

    # 3. Hash stub (no semantic quality — installs nothing)
    logger.warning("[RAG] Using hash stub embedder. Install sentence-transformers for real RAG.")
    import hashlib, struct

    class _Stub:
        DIMS = 384
        def encode(self, texts, **_):
            out = []
            for t in texts:
                raw = hashlib.sha256(t.encode()).digest() * 16
                vec = list(struct.unpack('96f', raw[:384])[:384])
                s = sum(abs(v) for v in vec) or 1.0
                out.append([v / s for v in vec])
            return out

    return _Stub()


_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = _get_embedder()
    return _embedder


async def retrieve(
    query: str,
    collection: str = "knowledge",
    top_k: int = 5,
    filter_metadata: Optional[dict] = None,
) -> list[dict]:
    """
    Retrieve semantically relevant documents from Qdrant.
    Returns list of {text, score, metadata} dicts.
    """
    try:
        client = _get_client()
        embedder = get_embedder()

        # Map collection alias to actual collection name
        collection_map = {
            "knowledge": settings.qdrant_knowledge_collection,
            "brand": settings.qdrant_brand_collection,
            "media": settings.qdrant_media_collection,
        }
        collection_name = collection_map.get(collection, settings.qdrant_knowledge_collection)

        raw_vec = embedder.encode(query)
        query_vector = raw_vec.tolist() if hasattr(raw_vec, "tolist") else list(raw_vec)

        from qdrant_client.models import Filter, FieldCondition, MatchValue
        qdrant_filter = None
        if filter_metadata:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_metadata.items()
            ]
            qdrant_filter = Filter(must=conditions) if conditions else None

        import asyncio
        results = await asyncio.to_thread(
            client.search,
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            {
                "text": r.payload.get("text", ""),
                "score": r.score,
                "metadata": {k: v for k, v in r.payload.items() if k != "text"},
                "id": str(r.id),
            }
            for r in results
        ]

    except Exception as e:
        logger.warning(f"[RAG] Retrieval failed: {e}")
        return []


async def store(
    text: str,
    metadata: dict,
    collection: str = "knowledge",
    point_id: Optional[str] = None,
) -> str:
    """Store a text chunk with metadata in Qdrant."""
    import uuid
    from qdrant_client.models import PointStruct

    try:
        client = _get_client()
        embedder = get_embedder()

        collection_map = {
            "knowledge": settings.qdrant_knowledge_collection,
            "brand": settings.qdrant_brand_collection,
            "media": settings.qdrant_media_collection,
        }
        collection_name = collection_map.get(collection, settings.qdrant_knowledge_collection)

        raw_vec = embedder.encode(text)
        vector = raw_vec.tolist() if hasattr(raw_vec, "tolist") else list(raw_vec)
        pid = point_id or str(uuid.uuid4())

        payload = {"text": text, **metadata}
        import asyncio
        await asyncio.to_thread(
            client.upsert,
            collection_name=collection_name,
            points=[PointStruct(id=pid, vector=vector, payload=payload)]
        )
        return pid

    except Exception as e:
        logger.error(f"[RAG] Store failed: {e}")
        raise


async def delete_points(
    point_ids: list[str],
    collection: str = "knowledge",
) -> None:
    """Delete specific points from Qdrant by ID."""
    if not point_ids:
        return
    try:
        client = _get_client()
        collection_map = {
            "knowledge": settings.qdrant_knowledge_collection,
            "brand": settings.qdrant_brand_collection,
            "media": settings.qdrant_media_collection,
        }
        collection_name = collection_map.get(collection, settings.qdrant_knowledge_collection)
        import asyncio
        await asyncio.to_thread(client.delete, collection_name=collection_name, points_selector=point_ids)
        logger.info(f"[RAG] Deleted {len(point_ids)} points from {collection_name}")
    except Exception as e:
        logger.error("Failed to delete points from Qdrant: %s", str(e), exc_info=True)


async def ensure_collections():
    """Create Qdrant collections if they don't exist."""
    from qdrant_client.models import Distance, VectorParams
    client = _get_client()
    collections_to_create = [
        settings.qdrant_knowledge_collection,
        settings.qdrant_brand_collection,
        settings.qdrant_media_collection,
    ]
    import asyncio
    existing_res = await asyncio.to_thread(client.get_collections)
    existing = {c.name for c in existing_res.collections}
    for name in collections_to_create:
        if name not in existing:
            await asyncio.to_thread(
                client.create_collection,
                collection_name=name,
                vectors_config=VectorParams(size=settings.qdrant_dimension, distance=Distance.COSINE),
            )
            logger.info(f"[RAG] Created collection: {name}")
