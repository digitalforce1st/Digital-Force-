'use client'

import { useState, useEffect } from 'react'
import Sidebar from '@/components/Sidebar'
import Link from 'next/link'
import { Plus, Target, ArrowRight, Clock, Activity, CheckCircle2, AlertCircle, TrendingUp } from 'lucide-react'
import api from '@/lib/api'

const STATUS_CONFIG: Record<string, { label: string; cls: string; icon: React.ElementType }> = {
  planning:          { label: 'Planning',          cls: 'badge-planning',   icon: Clock },
  awaiting_approval: { label: 'Awaiting Approval', cls: 'badge-awaiting',   icon: AlertCircle },
  executing:         { label: 'Executing',          cls: 'badge-executing',  icon: Activity },
  monitoring:        { label: 'Monitoring',         cls: 'badge-monitoring', icon: TrendingUp },
  complete:          { label: 'Complete',           cls: 'badge-complete',   icon: CheckCircle2 },
  failed:            { label: 'Failed',             cls: 'badge-failed',     icon: AlertCircle },
}

const PLATFORM_EMOJIS: Record<string, string> = {
  linkedin: '💼', facebook: '👥', twitter: '🐦', tiktok: '🎵',
  instagram: '📸', youtube: '▶️',
}

const PRIORITY_COLORS: Record<string, string> = {
  urgent: '#EF4444', high: '#F59E0B', normal: '#A78BFA', low: '#94A3B8'
}

interface Goal {
  id: string; title: string; status: string; priority: string
  progress_percent: number; tasks_total: number; tasks_completed: number
  platforms: string[]; created_at: string; deadline?: string
}

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    api.goals.list().then(setGoals).finally(() => setLoading(false))
  }, [])

  const filtered = statusFilter ? goals.filter(g => g.status === statusFilter) : goals

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">

        <div className="flex items-center justify-between mb-8 animate-slide-up">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">Missions</h1>
            <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.875rem' }}>All goals managed by your AI agency</p>
          </div>
          <Link href="/goals/new" className="btn-primary"><Plus size={15} /> New Mission</Link>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
          {[{ id: '', label: `All (${goals.length})` }, ...Object.entries(STATUS_CONFIG).map(([id, v]) => ({
            id, label: `${v.label} (${goals.filter(g => g.status === id).length})`
          }))].map(tab => (
            <button key={tab.id} onClick={() => setStatusFilter(tab.id)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all duration-200 flex-shrink-0"
                    style={{
                      background: statusFilter === tab.id ? 'rgba(124,58,237,0.2)' : 'rgba(255,255,255,0.04)',
                      color: statusFilter === tab.id ? '#A78BFA' : 'rgba(255,255,255,0.5)',
                      border: `1px solid ${statusFilter === tab.id ? 'rgba(124,58,237,0.3)' : 'rgba(255,255,255,0.06)'}`,
                    }}>
              {tab.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex justify-center py-16">
            <div className="flex gap-1"><div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" /></div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="glass-panel p-16 flex flex-col items-center text-center">
            <Target size={40} className="mb-4 text-primary-400/40" />
            <h3 className="font-bold text-white/60 mb-2">No missions found</h3>
            <Link href="/goals/new" className="btn-primary mt-4"><Plus size={14} />Create Mission</Link>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((goal, i) => {
              const s = STATUS_CONFIG[goal.status] || { label: goal.status, cls: 'badge-paused', icon: Clock }
              const Icon = s.icon
              return (
                <Link key={goal.id} href={`/goals/${goal.id}`}
                      className="glass-panel p-5 flex items-center gap-5 hover:glass-panel-active cursor-pointer block animate-slide-up"
                      style={{ animationDelay: `${i * 40}ms` }}>

                  {/* Priority dot */}
                  <div className="w-2 h-2 rounded-full flex-shrink-0"
                       style={{ background: PRIORITY_COLORS[goal.priority] || '#A78BFA', boxShadow: `0 0 8px ${PRIORITY_COLORS[goal.priority] || '#A78BFA'}60` }} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <span className={s.cls}><Icon size={10} />{s.label}</span>
                      {goal.platforms.slice(0,4).map(p => (
                        <span key={p} className="text-sm">{PLATFORM_EMOJIS[p] || '📱'}</span>
                      ))}
                      {goal.deadline && (
                        <span className="text-xs ml-auto" style={{ color: 'rgba(255,255,255,0.3)' }}>
                          Due {new Date(goal.deadline).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    <div className="font-semibold text-sm text-white mb-3">{goal.title}</div>
                    <div className="flex items-center gap-4">
                      <div className="progress-bar flex-1">
                        <div className="progress-fill" style={{ width: `${goal.progress_percent}%` }} />
                      </div>
                      <span className="text-xs flex-shrink-0" style={{ color: 'rgba(255,255,255,0.35)' }}>
                        {goal.tasks_completed}/{goal.tasks_total}
                      </span>
                    </div>
                  </div>

                  <ArrowRight size={16} style={{ color: 'rgba(255,255,255,0.25)', flexShrink: 0 }} />
                </Link>
              )
            })}
          </div>
        )}
      </main>
    </div>
  )
}
