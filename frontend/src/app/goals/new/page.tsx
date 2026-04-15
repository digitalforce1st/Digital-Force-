'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import { Send, Target, Calendar, Sparkles, Loader2, AlertCircle } from 'lucide-react'
import api from '@/lib/api'

const PLATFORM_OPTIONS = [
  { id: 'linkedin',  label: 'LinkedIn',  emoji: '💼' },
  { id: 'facebook',  label: 'Facebook',  emoji: '👥' },
  { id: 'twitter',   label: 'X/Twitter', emoji: '🐦' },
  { id: 'instagram', label: 'Instagram', emoji: '📸' },
  { id: 'tiktok',    label: 'TikTok',    emoji: '🎵' },
  { id: 'youtube',   label: 'YouTube',   emoji: '▶️' },
]

const EXAMPLES = [
  'Schedule 50 Facebook posts of our summit flyers across this week, starting tomorrow',
  'Grow our LinkedIn following from 1,000 to 5,000 in the next 30 days',
  'Post our 10 product videos across TikTok, Instagram, and YouTube with platform-optimized captions',
  'Run a 2-week campaign advertising our annual summit using assets from our media library',
  'Create a thought leadership campaign on LinkedIn for our CEO, 1 post per day for 7 days',
]

export default function NewGoalPage() {
  const router = useRouter()
  const [description, setDescription] = useState('')
  const [platforms, setPlatforms] = useState<string[]>([])
  const [deadline, setDeadline] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const togglePlatform = (id: string) =>
    setPlatforms(prev => prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id])

  const handleSubmit = async () => {
    if (!description.trim()) { setError('Please describe your goal.'); return }
    setLoading(true)
    setError('')
    try {
      const goal = await api.goals.create({
        description: description.trim(),
        platforms: platforms.length > 0 ? platforms : undefined,
        deadline: deadline || undefined,
      })
      router.push(`/goals/${goal.id}`)
    } catch (e: any) {
      setError(e.message || 'Failed to create goal')
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto max-w-3xl">

        {/* Header */}
        <div className="mb-10 animate-slide-up">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-2xl flex items-center justify-center"
                 style={{ background: 'linear-gradient(135deg, #7C3AED 0%, #06B6D4 100%)' }}>
              <Target size={20} className="text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white">New Mission Brief</h1>
          </div>
          <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.9rem' }}>
            Tell the AI agency what you want to achieve. Be as specific or as broad as you like.
          </p>
        </div>

        {/* Goal input */}
        <div className="glass-panel p-6 mb-5 animate-slide-up">
          <label className="block text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Sparkles size={15} className="text-primary-400" />
            Describe your goal
          </label>
          <textarea
            className="df-textarea w-full min-h-[140px] font-mono text-sm"
            placeholder="e.g. Schedule 50 Facebook posts of our summit flyers this week, grow our LinkedIn following from 1000 to 5000 in 30 days, or post these 10 videos across TikTok and Instagram..."
            value={description}
            onChange={e => setDescription(e.target.value)}
          />

          {/* Examples */}
          <div className="mt-4">
            <div className="text-xs font-medium mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>
              Try an example:
            </div>
            <div className="flex flex-col gap-1.5">
              {EXAMPLES.slice(0, 3).map((ex, i) => (
                <button key={i} onClick={() => setDescription(ex)}
                        className="text-left text-xs px-3 py-2 rounded-lg transition-all duration-200"
                        style={{ color: 'rgba(255,255,255,0.5)', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
                        onMouseEnter={e => (e.currentTarget.style.color = '#A78BFA')}
                        onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.5)')}>
                  → {ex}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Platform selection */}
        <div className="glass-panel p-6 mb-5 animate-slide-up">
          <label className="block text-sm font-semibold text-white mb-4">
            Target platforms <span className="font-normal" style={{ color: 'rgba(255,255,255,0.35)' }}>(optional — agent will decide if left empty)</span>
          </label>
          <div className="grid grid-cols-3 gap-2">
            {PLATFORM_OPTIONS.map(p => (
              <button key={p.id}
                      onClick={() => togglePlatform(p.id)}
                      className={`flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200 ${
                        platforms.includes(p.id) ? 'text-white' : 'text-white/50'
                      }`}
                      style={{
                        background: platforms.includes(p.id) ? 'rgba(124,58,237,0.2)' : 'rgba(255,255,255,0.03)',
                        border: `1px solid ${platforms.includes(p.id) ? 'rgba(124,58,237,0.4)' : 'rgba(255,255,255,0.07)'}`,
                      }}>
                <span>{p.emoji}</span>
                <span>{p.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Deadline */}
        <div className="glass-panel p-6 mb-6 animate-slide-up">
          <label className="block text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Calendar size={15} className="text-primary-400" />
            Deadline <span className="font-normal" style={{ color: 'rgba(255,255,255,0.35)' }}>(optional)</span>
          </label>
          <input
            type="date"
            className="df-input"
            value={deadline}
            onChange={e => setDeadline(e.target.value)}
            min={new Date().toISOString().split('T')[0]}
          />
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 p-4 rounded-xl flex items-center gap-3"
               style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)' }}>
            <AlertCircle size={16} className="text-red-400 flex-shrink-0" />
            <span className="text-sm text-red-300">{error}</span>
          </div>
        )}

        {/* Submit */}
        <div className="flex items-center gap-4">
          <button onClick={handleSubmit} disabled={loading || !description.trim()} className="btn-primary px-8 py-3 text-base">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
            {loading ? 'Briefing the Agent...' : 'Brief the Agency'}
          </button>
          {loading && (
            <p className="text-sm" style={{ color: 'rgba(255,255,255,0.4)' }}>
              Agent is analyzing your goal and building a campaign plan...
            </p>
          )}
        </div>

        {loading && (
          <div className="mt-6 glass-panel p-6 animate-fade-in">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex gap-1">
                <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
              </div>
              <span className="text-sm font-medium text-white">Agent is thinking...</span>
            </div>
            <div className="space-y-2 text-sm" style={{ color: 'rgba(255,255,255,0.5)' }}>
              <div>→ Parsing goal and extracting intent...</div>
              <div>→ Researching trending content and audience data...</div>
              <div>→ Building your campaign plan...</div>
              <div style={{ color: 'rgba(255,255,255,0.25)' }}>→ You'll be redirected when the plan is ready for review.</div>
            </div>
          </div>
        )}

      </main>
    </div>
  )
}
