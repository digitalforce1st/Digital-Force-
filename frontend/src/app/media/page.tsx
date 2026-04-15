'use client'

import { useState, useCallback, useEffect } from 'react'
import Sidebar from '@/components/Sidebar'
import { Upload, Trash2, Image as ImageIcon, Video, Music, FileText, Loader2, Filter } from 'lucide-react'
import api, { MediaAsset } from '@/lib/api'

const TYPE_FILTER = [
  { id: '', label: 'All' },
  { id: 'image', label: 'Images', icon: ImageIcon },
  { id: 'video', label: 'Videos', icon: Video },
  { id: 'audio', label: 'Audio', icon: Music },
  { id: 'pdf', label: 'PDFs', icon: FileText },
]

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function MediaPage() {
  const [assets, setAssets] = useState<MediaAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<MediaAsset | null>(null)
  const [dragging, setDragging] = useState(false)

  const loadAssets = async () => {
    try {
      const data = await api.media.list()
      setAssets(data)
    } finally { setLoading(false) }
  }

  useEffect(() => { loadAssets() }, [filter])

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    for (const file of Array.from(files)) {
      const fd = new FormData()
      fd.append('file', file)
      try { await api.media.upload(fd) } catch (e) { console.error(e) }
    }
    setUploading(false)
    loadAssets()
  }

  const handleDelete = async (id: string) => {
    await api.media.delete(id)
    setAssets(prev => prev.filter(a => a.id !== id))
    if (selected?.id === id) setSelected(null)
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    handleUpload(e.dataTransfer.files)
  }, [])

  const filtered = filter ? assets.filter(a => a.asset_type === filter) : assets

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">

        {/* Header */}
        <div className="p-8 pb-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">Media Library</h1>
            <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.875rem' }}>
              Upload flyers, videos, and assets for your campaigns
            </p>
          </div>
          <div>
            <label className="btn-primary cursor-pointer">
              <input type="file" multiple className="hidden" accept="image/*,video/*,audio/*,.pdf"
                     onChange={e => handleUpload(e.target.files)} />
              {uploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
              {uploading ? 'Uploading...' : 'Upload Assets'}
            </label>
          </div>
        </div>

        {/* Filter bar */}
        <div className="px-8 pb-4 flex items-center gap-2">
          <Filter size={14} style={{ color: 'rgba(255,255,255,0.3)' }} />
          {TYPE_FILTER.map(t => (
            <button key={t.id} onClick={() => setFilter(t.id)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200"
                    style={{
                      background: filter === t.id ? 'rgba(124,58,237,0.2)' : 'rgba(255,255,255,0.04)',
                      color: filter === t.id ? '#A78BFA' : 'rgba(255,255,255,0.5)',
                      border: `1px solid ${filter === t.id ? 'rgba(124,58,237,0.3)' : 'rgba(255,255,255,0.06)'}`,
                    }}>
              {t.label}
            </button>
          ))}
          <span className="ml-auto text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>{filtered.length} assets</span>
        </div>

        <div className="flex flex-1 overflow-hidden gap-6 px-8 pb-8">

          {/* Grid */}
          <div className="flex-1 overflow-y-auto"
               onDragOver={e => { e.preventDefault(); setDragging(true) }}
               onDragLeave={() => setDragging(false)}
               onDrop={handleDrop}>

            {/* Drop zone hint */}
            {dragging && (
              <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
                   style={{ background: 'rgba(124,58,237,0.15)', border: '2px dashed rgba(124,58,237,0.6)' }}>
                <div className="text-2xl font-bold text-primary-400">Drop files to upload</div>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center h-48">
                <div className="flex gap-1"><div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" /></div>
              </div>
            ) : filtered.length === 0 ? (
              <div className="border-2 border-dashed rounded-3xl p-16 flex flex-col items-center justify-center text-center"
                   style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                <Upload size={36} className="mb-4" style={{ color: 'rgba(255,255,255,0.2)' }} />
                <div className="font-semibold text-white/50 mb-1">No assets yet</div>
                <div className="text-sm" style={{ color: 'rgba(255,255,255,0.25)' }}>Drag & drop files or click "Upload Assets"</div>
              </div>
            ) : (
              <div className="grid grid-cols-4 gap-3">
                {filtered.map(asset => (
                  <button key={asset.id} onClick={() => setSelected(asset)}
                          className="glass-panel overflow-hidden group text-left transition-all duration-200 hover:glass-panel-active"
                          style={{ aspectRatio: '1', position: 'relative' }}>

                    {/* Preview */}
                    {asset.asset_type === 'image' ? (
                      <img src={`${API_BASE}${asset.public_url}`} alt={asset.filename}
                           className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center"
                           style={{ background: 'rgba(255,255,255,0.03)' }}>
                        {asset.asset_type === 'video' ? <Video size={28} className="text-blue-400" />
                          : asset.asset_type === 'audio' ? <Music size={28} className="text-purple-400" />
                          : <FileText size={28} className="text-cyan-400" />}
                      </div>
                    )}

                    {/* Overlay */}
                    <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-2"
                         style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.8) 0%, transparent 60%)' }}>
                      <div className="text-xs text-white font-medium truncate">{asset.filename}</div>
                      <div className="text-[10px]" style={{ color: 'rgba(255,255,255,0.5)' }}>{formatBytes(asset.file_size_bytes)}</div>
                    </div>

                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Detail panel */}
          {selected && (
            <div className="w-72 flex-shrink-0">
              <div className="glass-panel p-5 space-y-4 sticky top-0">
                {/* Preview */}
                <div className="rounded-xl overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)', aspectRatio: '16/9' }}>
                  {selected.asset_type === 'image'
                    ? <img src={`${API_BASE}${selected.public_url}`} alt="" className="w-full h-full object-contain" />
                    : <div className="w-full h-full flex items-center justify-center">
                        <ImageIcon size={32} style={{ color: 'rgba(255,255,255,0.2)' }} />
                      </div>
                  }
                </div>

                <div>
                  <div className="font-semibold text-sm text-white truncate">{selected.filename}</div>
                  <div className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>
                    {selected.asset_type.toUpperCase()} · {formatBytes(selected.file_size_bytes)} · Used {selected.usage_count}x
                  </div>
                </div>

                {selected.ai_description && (
                  <div>
                    <div className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-1.5">AI Description</div>
                    <p className="text-xs leading-relaxed" style={{ color: 'rgba(255,255,255,0.5)' }}>{selected.ai_description}</p>
                  </div>
                )}

                {(selected.auto_tags ?? []).length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Tags</div>
                    <div className="flex flex-wrap gap-1.5">
                      {(selected.auto_tags ?? []).map(tag => (
                        <span key={tag} className="text-[11px] px-2 py-0.5 rounded-md"
                              style={{ background: 'rgba(124,58,237,0.1)', color: '#A78BFA' }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <button onClick={() => handleDelete(selected.id)}
                        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium text-red-400 transition-all"
                        style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
                  <Trash2 size={14} /> Delete Asset
                </button>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
