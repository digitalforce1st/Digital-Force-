'use client'

import { useState, useCallback } from 'react'
import Sidebar from '@/components/Sidebar'
import { Upload, Link, FileText, Image, Video, Music, Table, Loader2, CheckCircle2, Trash2, AlertCircle, Plus } from 'lucide-react'
import api, { TrainingDoc } from '@/lib/api'

// Use canonical TrainingDoc from api.ts
type KnowledgeItem = TrainingDoc

const CATEGORIES = [
  { id: 'brand_voice',      label: 'Brand Voice',      desc: 'How we sound and communicate' },
  { id: 'product_info',     label: 'Product/Service',  desc: 'What we offer' },
  { id: 'market_research',  label: 'Market Research',  desc: 'Industry trends & insights' },
  { id: 'content_examples', label: 'Content Examples', desc: 'Posts that worked well' },
  { id: 'competitor',       label: 'Competitor Intel', desc: 'What competitors are doing' },
  { id: 'other',            label: 'Other',            desc: 'General knowledge' },
]

const TYPE_ICONS: Record<string, React.ElementType> = {
  pdf: FileText, url: Link, image: Image, video: Video,
  audio: Music, csv: Table, docx: FileText, text: FileText,
}

const STATUS_STYLES: Record<string, { color: string; bg: string }> = {
  indexed:    { color: '#34D399', bg: 'rgba(16,185,129,0.1)' },
  processing: { color: '#A78BFA', bg: 'rgba(124,58,237,0.1)' },
  failed:     { color: '#F87171', bg: 'rgba(239,68,68,0.1)' },
  pending:    { color: '#94A3B8', bg: 'rgba(148,163,184,0.1)' },
}

export default function TrainingPage() {
  const [items, setItems] = useState<KnowledgeItem[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [tab, setTab] = useState<'upload' | 'url' | 'text'>('upload')
  const [url, setUrl] = useState('')
  const [rawText, setRawText] = useState('')
  const [category, setCategory] = useState('brand_voice')
  const [title, setTitle] = useState('')
  const [dragging, setDragging] = useState(false)
  const [successMsg, setSuccessMsg] = useState('')

  const loadItems = async () => {
    if (loaded) return
    setLoading(true)
    try {
      const data = await api.training.list()
      setItems(data)
      setLoaded(true)
    } finally { setLoading(false) }
  }

  const refreshItems = async () => {
    const data = await api.training.list()
    setItems(data)
  }

  useState(() => { loadItems() })

  const showSuccess = (msg: string) => {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 4000)
  }

  const handleFileUpload = async (file: File) => {
    setUploading(true)
    const fd = new FormData()
    fd.append('file', file)
    fd.append('category', category)
    fd.append('title', title || file.name)
    try {
      await api.training.upload(fd)
      showSuccess(`"${file.name}" is being indexed into the knowledge base`)
      setTimeout(refreshItems, 1500)
    } catch (e: any) {
      console.error(e)
    } finally { setUploading(false) }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFileUpload(file)
  }, [category, title])

  const handleUrlIngest = async () => {
    if (!url.trim()) return
    setUploading(true)
    try {
      await api.training.uploadUrl(url.trim(), category)
      showSuccess(`URL "${url}" is being scraped and indexed`)
      setUrl('')
      setTimeout(refreshItems, 1500)
    } catch (e: any) { console.error(e) }
    finally { setUploading(false) }
  }

  const handleTextIngest = async () => {
    if (!rawText.trim()) return
    setUploading(true)
    const fd = new FormData()
    fd.append('raw_text', rawText.trim())
    fd.append('category', category)
    fd.append('title', title || 'Text Input')
    try {
      await api.training.upload(fd)
      showSuccess('Text indexed into knowledge base')
      setRawText('')
    } catch (e: any) { console.error(e) }
    finally { setUploading(false) }
  }

  const handleDelete = async (id: string) => {
    await api.training.delete(id)
    setItems(prev => prev.filter(i => i.id !== id))
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">

        <div className="mb-8 animate-slide-up">
          <h1 className="text-2xl font-bold text-white mb-1">Knowledge Base</h1>
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.875rem' }}>
            Train your AI agency with brand documents, URLs, images, videos, and more.
          </p>
        </div>

        {successMsg && (
          <div className="mb-5 p-4 rounded-xl flex items-center gap-3 animate-slide-up"
               style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.3)' }}>
            <CheckCircle2 size={16} className="text-green-400" />
            <span className="text-sm text-green-300">{successMsg}</span>
          </div>
        )}

        <div className="grid grid-cols-5 gap-6">

          {/* Upload panel */}
          <div className="col-span-2 space-y-5">

            {/* Category */}
            <div className="glass-panel p-5">
              <label className="block text-xs font-semibold text-white/60 uppercase tracking-wider mb-3">Category</label>
              <div className="space-y-1.5">
                {CATEGORIES.map(c => (
                  <button key={c.id} onClick={() => setCategory(c.id)}
                          className="w-full text-left px-4 py-2.5 rounded-xl text-sm transition-all duration-200"
                          style={{
                            background: category === c.id ? 'rgba(124,58,237,0.2)' : 'rgba(255,255,255,0.03)',
                            border: `1px solid ${category === c.id ? 'rgba(124,58,237,0.4)' : 'rgba(255,255,255,0.06)'}`,
                            color: category === c.id ? '#A78BFA' : 'rgba(255,255,255,0.6)',
                          }}>
                    <div className="font-medium">{c.label}</div>
                    <div className="text-[11px] opacity-60 mt-0.5">{c.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Upload type tabs */}
            <div className="glass-panel p-5">
              <div className="flex gap-1 mb-4 p-1 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)' }}>
                {(['upload', 'url', 'text'] as const).map(t => (
                  <button key={t} onClick={() => setTab(t)}
                          className="flex-1 py-2 px-3 rounded-lg text-xs font-semibold capitalize transition-all duration-200"
                          style={{
                            background: tab === t ? 'rgba(124,58,237,0.3)' : 'transparent',
                            color: tab === t ? '#A78BFA' : 'rgba(255,255,255,0.4)',
                          }}>
                    {t === 'upload' ? '📁 File' : t === 'url' ? '🔗 URL' : '📝 Text'}
                  </button>
                ))}
              </div>

              {tab === 'upload' && (
                <div
                  className="border-2 border-dashed rounded-2xl p-8 text-center transition-all duration-200 cursor-pointer"
                  style={{ borderColor: dragging ? '#7C3AED' : 'rgba(255,255,255,0.1)', background: dragging ? 'rgba(124,58,237,0.05)' : 'transparent' }}
                  onDragOver={e => { e.preventDefault(); setDragging(true) }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => document.getElementById('file-input')?.click()}>
                  <input id="file-input" type="file" className="hidden"
                    accept=".pdf,.docx,.doc,.txt,.md,.png,.jpg,.jpeg,.mp4,.mov,.csv,.xlsx,.mp3,.wav"
                    onChange={e => e.target.files?.[0] && handleFileUpload(e.target.files[0])} />
                  {uploading
                    ? <Loader2 size={28} className="animate-spin mx-auto mb-3 text-primary-400" />
                    : <Upload size={28} className="mx-auto mb-3" style={{ color: 'rgba(255,255,255,0.3)' }} />}
                  <div className="text-sm font-medium text-white/60">Drop file or click to browse</div>
                  <div className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
                    PDF, DOCX, TXT, Images, Videos, CSV, Audio
                  </div>
                </div>
              )}

              {tab === 'url' && (
                <div className="space-y-3">
                  <input className="df-input" placeholder="https://example.com/article" value={url} onChange={e => setUrl(e.target.value)} />
                  <button onClick={handleUrlIngest} disabled={uploading || !url.trim()} className="btn-primary w-full justify-center">
                    {uploading ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
                    Ingest URL
                  </button>
                </div>
              )}

              {tab === 'text' && (
                <div className="space-y-3">
                  <input className="df-input" placeholder="Optional title..." value={title} onChange={e => setTitle(e.target.value)} />
                  <textarea className="df-textarea w-full" placeholder="Paste text, brand guidelines, product descriptions..." value={rawText} onChange={e => setRawText(e.target.value)} />
                  <button onClick={handleTextIngest} disabled={uploading || !rawText.trim()} className="btn-primary w-full justify-center">
                    {uploading ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
                    Add to Knowledge Base
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Knowledge items list */}
          <div className="col-span-3">
            <div className="glass-panel overflow-hidden">
              <div className="p-5 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-white text-sm">{items.length} knowledge items</span>
                  <button onClick={refreshItems} className="btn-ghost text-xs">Refresh</button>
                </div>
              </div>

              {loading ? (
                <div className="flex items-center justify-center p-12">
                  <div className="flex gap-1"><div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" /></div>
                </div>
              ) : items.length === 0 ? (
                <div className="flex flex-col items-center p-12 text-center">
                  <AlertCircle size={32} className="mb-3" style={{ color: 'rgba(255,255,255,0.2)' }} />
                  <div className="text-sm font-medium text-white/50">No knowledge items yet</div>
                  <div className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.25)' }}>Upload documents to teach the agent about your brand</div>
                </div>
              ) : (
                <div className="divide-y" style={{ '--tw-divide-opacity': '1' } as any}>
                  {items.map(item => {
                    const Icon = TYPE_ICONS[item.source_type] || FileText
                    const s = STATUS_STYLES[item.processing_status] || STATUS_STYLES.pending
                    return (
                      <div key={item.id} className="flex items-center gap-4 px-5 py-4 hover:bg-white/[0.02] transition-colors">
                        <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                             style={{ background: 'rgba(124,58,237,0.1)' }}>
                          <Icon size={16} className="text-primary-400" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-white truncate">{item.title}</div>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[11px]" style={{ color: 'rgba(255,255,255,0.35)' }}>{item.source_type.toUpperCase()}</span>
                            <span className="text-[11px]" style={{ color: 'rgba(255,255,255,0.25)' }}>·</span>
                            <span className="text-[11px]" style={{ color: 'rgba(255,255,255,0.35)' }}>{(item.category ?? 'other').replace('_', ' ')}</span>
                            {item.chunk_count > 0 && (
                              <><span style={{ color: 'rgba(255,255,255,0.25)' }}>·</span>
                              <span className="text-[11px]" style={{ color: 'rgba(255,255,255,0.35)' }}>{item.chunk_count} chunks</span></>
                            )}
                          </div>
                        </div>
                        <span className="text-[11px] px-2 py-1 rounded-lg font-semibold flex-shrink-0"
                              style={{ background: s.bg, color: s.color }}>
                          {item.processing_status === 'processing' ? '⟳ ' : ''}{item.processing_status}
                        </span>
                        <button onClick={() => handleDelete(item.id)} className="btn-ghost p-2 text-red-400/50 hover:text-red-400">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
