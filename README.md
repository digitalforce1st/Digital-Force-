# Digital Force

**Autonomous Digital Media Intelligent Agency**

> Give it a goal. Watch it work.

Digital Force is a tier-one, fully autonomous multi-agent AI platform that seamlessly manages your entire social media presence. Brief the agency in natural language, and its neural network of specialized agents will plan, create, publish, monitor, and iteratively optimize your digital footprint.

## Architecture: Digital Force 2.0 (LangClaw)

Digital Force utilizes a custom-built, highly scalable orchestration engine known as **LangClaw**. 
Migrating away from the memory-heavy routing of standard LangGraph `StateGraph` implementations, our LangClaw architecture operates on a strict **"Pass IDs, Not Objects"** paradigm. 

- **The Omniscient Chat God-Node**: Ad-hoc conversational requests are handled by a lightweight ReAct loop that natively reads Postgres and Qdrant memory, writing actions directly to the database without state bloat.
- **The Campaign Hub**: Rigid workflows (Strategy -> Research -> Content Generation -> Publishing) are completely isolated. LangClaw sequences our specialized worker nodes via direct ID passing, eliminating Out-Of-Memory (OOM) crashes during heavy multi-modal generation.
- **The Internal Monologue**: A continuously running, randomized, background worker (`monologue_worker.py`) proactively researches industry trends. It scores relevance thresholds internally, silencing noise as *Episodic Memory* in Qdrant, and only pushing high-value insights to the user interface.

## Core Capabilities

- **Natural Language Directives** — "Grow LinkedIn from 1K to 10K followers in 30 days"
- **Multi-Agent Swarm** — A unified team of specific AI models (Strategist, Writer, Designer, Publisher, Monitor, Auditor)
- **Omniscient RAG** — Ingests and learns your brand voice from PDFs, URLs, videos, docs, and prior campaigns.
- **Unified Knowledge Brain** — Consolidates raw training ingestion and media library management.
- **Universal Broadcasting** — Automated publishing via Buffer API and Facebook Graph API.
- **SkillForge (Self-Evolving)** — The agent actively writes, tests, and deploys its own Python capability scripts in a local sandbox to solve novel user requests.

## Tech Stack

- **Backend:** FastAPI + Python 3.12
- **Orchestration:** LangClaw Hub (Digital Force 2.0)
- **Intelligence:** Groq Ecosystem (Llama-3.3-70b/Versatile) + GPT-4o + CLIP + Whisper
- **Memory & Vectorization:** Qdrant (Episodic & Semantic Storage)
- **Database:** Full Async PostgreSQL + SQLAlchemy
- **Frontend:** Next.js 14 + Framer Motion (Glassmorphic Neumorphism)
- **Execution:** Persistent Local Sandbox execution via Python Subprocesses

## Status

**In active development** — Architecting the undisputed future of autonomous digital intelligence. 
