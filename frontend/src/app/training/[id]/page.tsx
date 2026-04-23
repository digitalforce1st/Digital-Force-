'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/Sidebar'
import {
  ArrowLeft, BookOpen, RefreshCw, Trash2, AlertCircle,
  CheckCircle2, Clock, FileText, Tag, Hash, AlertTriangle,
} from 'lucide-react'
import api, { TrainingDoc } from '@/lib/api'

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  indexed:    { label: 'Indexed',    color: '#34D399', bg: 'rgba(52,211,153,0.12)',  icon: CheckCircle2 },
  processing: { label: 'Processing', color: '#A78BFA', bg: 'rgba(167,139,250,0.12)', icon: RefreshCw },
  pending:    { label: 'Pending',    color: '#FCD34D', bg: 'rgba(252,211,77,0.12)',   icon: Clock },
  failed:     { label: 'Failed',     color: '#F87171', bg: 'rgba(248,113,113,0.12)',  icon: AlertTriangle },
}

export default function TrainingDocDetailPage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()

  const [doc, setDoc] = useState<TrainingDoc | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reindexing, setReindexing] = useState(false)
  const [reindexResult, setReindexResult] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    api.training.get(id)
      .then(setDoc)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  const handleReindex = async () => {
    setReindexing(true)
    setReindexResult('')
    try {
      const res = await api.training.reindex(id)
      setReindexResult(res.message || 'Re-indexing complete.')
      // Refresh doc
      const updated = await api.training.get(id)
      setDoc(updated)
    } catch (e: unknown) {
      setReindexResult(e instanceof Error ? e.message : 'Re-indexing failed')
    } finally {
      setReindexing(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setDeleting(true)
    try {
      await api.training.delete(id)
      router.push('/training')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Delete failed')
      setDeleting(false)
    }
  }

  if (loading) return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" />
        </div>
      </main>
    </div>
  )

  if (error && !doc) return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
        <AlertCircle size={40} style={{ color: '#FCA5A5' }} />
        <div style={{ color: '#fff', fontWeight: 600 }}>Failed to load document</div>
        <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.875rem' }}>{error}</div>
        <Link href="/training" className="btn-ghost">← Back to Knowledge Base</Link>
      </main>
    </div>
  )

  if (!doc) return null

  const statusCfg = STATUS_CONFIG[doc.processing_status] || STATUS_CONFIG.pending
  const StatusIcon = statusCfg.icon
  const tags: string[] = Array.isArray(doc.tags) ? doc.tags : []

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
        <div style={{ maxWidth: 860, margin: '0 auto' }}>

          {/* Back */}
          <Link href="/training" className="btn-ghost" style={{ marginBottom: '1.5rem', display: 'inline-flex' }}>
            <ArrowLeft size={14} /> Back to Knowledge Base
          </Link>

          {/* Header card */}
          <div className="glass-panel" style={{ padding: '1.75rem', marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
              <div style={{
                width: 52, height: 52, borderRadius: 14, flexShrink: 0,
                background: 'rgba(124,58,237,0.12)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <BookOpen size={24} style={{ color: '#A78BFA' }} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h1 style={{
                  fontSize: '1.3rem', fontWeight: 700, color: '#fff',
                  marginBottom: 6, lineHeight: 1.3,
                }}>
                  {doc.title}
                </h1>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{
                    fontSize: '0.75rem', padding: '0.2rem 0.6rem', borderRadius: 6,
                    background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.5)',
                    textTransform: 'capitalize',
                  }}>
                    <FileText size={11} style={{ display: 'inline', marginRight: 4 }} />
                    {doc.source_type}
                  </span>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    fontSize: '0.75rem', padding: '0.2rem 0.6rem', borderRadius: 6,
                    background: statusCfg.bg, color: statusCfg.color,
                  }}>
                    <StatusIcon size={11} />
                    {statusCfg.label}
                  </span>
                  {doc.category && (
                    <span style={{
                      fontSize: '0.75rem', padding: '0.2rem 0.6rem', borderRadius: 6,
                      background: 'rgba(34,211,238,0.1)', color: '#22D3EE',
                      textTransform: 'capitalize',
                    }}>
                      <Tag size={10} style={{ display: 'inline', marginRight: 4 }} />
                      {doc.category.replace('_', ' ')}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Stats row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.25rem' }}>
            {[
              { label: 'Chunks Indexed', value: doc.chunk_count, color: '#A78BFA' },
              { label: 'Source Type', value: doc.source_type.toUpperCase(), color: '#22D3EE' },
              { label: 'Added', value: new Date(doc.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }), color: '#34D399' },
            ].map(item => (
              <div key={item.label} className="glass-panel" style={{ padding: '1.25rem', textAlign: 'center' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: item.color, marginBottom: 4 }}>
                  {item.value}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)' }}>{item.label}</div>
              </div>
            ))}
          </div>

          {/* Summary */}
          {doc.content_summary && (
            <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.25rem' }}>
              <div style={{ fontWeight: 600, color: '#fff', marginBottom: '0.875rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileText size={15} style={{ color: '#A78BFA' }} />
                AI-Generated Summary
              </div>
              <div style={{
                color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem', lineHeight: 1.75,
                padding: '1rem', background: 'rgba(255,255,255,0.02)',
                borderRadius: 10, border: '1px solid rgba(255,255,255,0.05)',
              }}>
                {doc.content_summary}
              </div>
            </div>
          )}

          {/* Tags */}
          {tags.length > 0 && (
            <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '1.25rem' }}>
              <div style={{ fontWeight: 600, color: '#fff', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Hash size={14} style={{ color: '#22D3EE' }} />
                Tags
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {tags.map((tag, i) => (
                  <span key={i} style={{
                    fontSize: '0.78rem', padding: '0.25rem 0.7rem', borderRadius: 20,
                    background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.55)',
                    border: '1px solid rgba(255,255,255,0.08)',
                  }}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1rem' }}>Actions</div>

            {/* Re-index */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '1rem', borderRadius: 12,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
              marginBottom: '0.75rem',
            }}>
              <div>
                <div style={{ fontWeight: 500, color: '#fff', fontSize: '0.9rem' }}>Re-embed Document</div>
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem', marginTop: 2 }}>
                  Re-runs the embedding pipeline. Use when content has changed.
                </div>
                {reindexResult && (
                  <div style={{ marginTop: 8, fontSize: '0.8rem', color: '#34D399' }}>
                    ✓ {reindexResult}
                  </div>
                )}
              </div>
              <button
                id="reindex-doc"
                onClick={handleReindex}
                disabled={reindexing}
                className="btn-secondary"
                style={{ flexShrink: 0, gap: 6, opacity: reindexing ? 0.7 : 1 }}
              >
                <RefreshCw size={14} style={{ animation: reindexing ? 'spin 1s linear infinite' : 'none' }} />
                {reindexing ? 'Re-indexing...' : 'Re-embed'}
              </button>
            </div>

            {/* Delete */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '1rem', borderRadius: 12,
              background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.12)',
            }}>
              <div>
                <div style={{ fontWeight: 500, color: '#FCA5A5', fontSize: '0.9rem' }}>Delete Document</div>
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem', marginTop: 2 }}>
                  {confirmDelete
                    ? '⚠️ This is permanent. The document and all its embeddings will be removed.'
                    : 'Remove this document from the knowledge base permanently.'}
                </div>
                {error && (
                  <div style={{ marginTop: 8, fontSize: '0.8rem', color: '#FCA5A5' }}>{error}</div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                {confirmDelete && (
                  <button onClick={() => setConfirmDelete(false)} className="btn-ghost" style={{ fontSize: '0.82rem' }}>
                    Cancel
                  </button>
                )}
                <button
                  id="delete-doc"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="btn-danger"
                  style={{ gap: 6, opacity: deleting ? 0.7 : 1 }}
                >
                  <Trash2 size={14} />
                  {deleting ? 'Deleting...' : confirmDelete ? 'Confirm Delete' : 'Delete'}
                </button>
              </div>
            </div>
          </div>

        </div>
      </main>
    </div>
  )
}
