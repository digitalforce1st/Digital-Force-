'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import Link from 'next/link'
import {
  CheckCircle2, XCircle, Clock, Activity, AlertCircle,
  ArrowLeft, Bot, User, Loader2, ChevronDown, ChevronUp,
  Zap, Target, Calendar
} from 'lucide-react'
import api, { Goal as ApiGoal } from '@/lib/api'
import { getToken } from '@/lib/auth'

const AGENT_COLORS: Record<string, string> = {
  orchestrator:    '#7C3AED',
  researcher:      '#06B6D4',
  strategist:      '#F59E0B',
  content_director:'#10B981',
  visual_designer: '#EC4899',
  publisher:       '#3B82F6',
  skillforge:      '#EF4444',
  monitor:        '#94A3B8',
  human:           '#F8F8FF',
}

const AGENT_LABELS: Record<string, string> = {
  orchestrator: 'Orchestrator',
  researcher:   'Researcher',
  strategist:   'Strategist',
  content_director: 'Content Director',
  visual_designer:  'Visual Designer',
  publisher:    'Publisher',
  skillforge:   'SkillForge',
  monitor:      'Monitor',
  human:        'Human',
}

interface AgentLogEntry {
  id: string
  agent: string
  level: string
  thought: string
  action?: string
  created_at: string
}

// Use canonical Goal from api.ts — plan tasks use CampaignTask shape (title/content_type)
type Goal = ApiGoal

export default function GoalDetailPage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()
  const [goal, setGoal] = useState<Goal | null>(null)
  const [logs, setLogs] = useState<AgentLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [approving, setApproving] = useState(false)
  const [notes, setNotes] = useState('')
  const [showPlan, setShowPlan] = useState(true)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // Fetch goal data
  const fetchGoal = async () => {
    try {
      const data = await api.goals.get(id)
      setGoal(data)
      setLogs(data.agent_logs || [])
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    fetchGoal().finally(() => setLoading(false))

    // Poll every 3 seconds for active goals
    const interval = setInterval(() => {
      fetchGoal()
    }, 3000)

    return () => clearInterval(interval)
  }, [id])

  // SSE stream for live logs — pass token as query param since EventSource doesn't support headers
  useEffect(() => {
    const token = getToken()
    const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const url = `${BASE}/api/stream/goals/${id}${token ? `?token=${token}` : ''}`
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        if (event.type === 'agent_log') {
          setLogs(prev => {
            const exists = prev.some(l => l.thought === event.thought && l.agent === event.agent)
            if (exists) return prev
            return [...prev, {
              id: Math.random().toString(),
              agent: event.agent,
              level: event.level,
              thought: event.thought,
              action: event.action,
              created_at: event.timestamp,
            }].slice(-100)
          })
          logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
        }
      } catch {}
    }

    es.onerror = () => es.close()
    return () => es.close()
  }, [id])

  const handleApprove = async (approved: boolean) => {
    setApproving(true)
    try {
      await api.goals.approve(id, { approved, notes: notes || undefined })
      await fetchGoal()
    } catch (e) {
      console.error(e)
    } finally {
      setApproving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center">
          <div className="flex gap-1.5">
            <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
          </div>
        </main>
      </div>
    )
  }

  if (!goal) return null

  const isActive = ['planning','executing','monitoring'].includes(goal.status)
  const needsApproval = goal.status === 'awaiting_approval'

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">

        {/* Top bar */}
        <div className="sticky top-0 z-10 px-8 py-4 border-b flex items-center gap-4"
             style={{ background: 'rgba(15,15,26,0.95)', borderColor: 'rgba(255,255,255,0.06)', backdropFilter: 'blur(12px)' }}>
          <Link href="/goals" className="btn-ghost"><ArrowLeft size={15} /> Back</Link>
          <div className="flex-1 min-w-0">
            <h1 className="font-bold text-white truncate">{goal.title}</h1>
          </div>
          {isActive && (
            <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full"
                 style={{ background: 'rgba(124,58,237,0.15)', color: '#A78BFA', border: '1px solid rgba(124,58,237,0.25)' }}>
              <div className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
              Live
            </div>
          )}
        </div>

        <div className="p-8 grid grid-cols-5 gap-6">

          {/* Main content — left 3 cols */}
          <div className="col-span-3 space-y-5">

            {/* Progress */}
            <div className="glass-panel p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Target size={18} className="text-primary-400" />
                  <span className="font-semibold text-white">Mission Progress</span>
                </div>
                <span className="text-lg font-bold text-white">{Math.round(goal.progress_percent)}%</span>
              </div>
              <div className="progress-bar w-full mb-3">
                <div className="progress-fill" style={{ width: `${goal.progress_percent}%` }} />
              </div>
              <div className="flex gap-4 text-xs" style={{ color: 'rgba(255,255,255,0.4)' }}>
                <span>✅ {goal.tasks_completed} done</span>
                <span>⏳ {goal.tasks_total - goal.tasks_completed - goal.tasks_failed} pending</span>
                {goal.tasks_failed > 0 && <span className="text-red-400">❌ {goal.tasks_failed} failed</span>}
              </div>
            </div>

            {/* Approval panel */}
            {needsApproval && goal.plan && (
              <div className="glass-panel p-6 animate-pulse-glow" style={{ borderColor: 'rgba(245,158,11,0.4)' }}>
                <div className="flex items-center gap-3 mb-5">
                  <AlertCircle size={20} className="text-amber-400" />
                  <div>
                    <div className="font-bold text-white">Plan Ready for Review</div>
                    <div className="text-xs text-amber-400/70 mt-0.5">Review and approve before execution begins</div>
                  </div>
                </div>

                <div className="mb-4 p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)' }}>
                  <div className="font-semibold text-white text-sm mb-1">{goal.plan.campaign_name}</div>
                  <p className="text-sm" style={{ color: 'rgba(255,255,255,0.5)' }}>{goal.plan.campaign_summary}</p>
                  <div className="flex gap-4 mt-3 text-xs" style={{ color: 'rgba(255,255,255,0.4)' }}>
                    <span>📝 {goal.plan.tasks?.length || 0} tasks planned</span>
                    <span>📅 {goal.plan.duration_days || 7} days</span>
                  </div>
                </div>

                <textarea
                  className="df-textarea w-full mb-4 min-h-[70px]"
                  placeholder="Add feedback or modifications (optional)..."
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                />

                <div className="flex gap-3">
                  <button onClick={() => handleApprove(true)} disabled={approving}
                          className="btn-primary flex-1 py-3 justify-center">
                    {approving ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                    Approve & Execute
                  </button>
                  <button onClick={() => handleApprove(false)} disabled={approving} className="btn-secondary px-5">
                    <XCircle size={16} />
                    Revise
                  </button>
                </div>
              </div>
            )}

            {/* Campaign Plan */}
            {goal.plan?.tasks && goal.plan.tasks.length > 0 && !needsApproval && (
              <div className="glass-panel overflow-hidden">
                <button className="w-full flex items-center justify-between p-5 text-sm font-semibold text-white"
                        onClick={() => setShowPlan(p => !p)}>
                  <span>Campaign Tasks ({goal.plan!.tasks!.length})</span>
                  {showPlan ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                </button>
                {showPlan && (
                  <div className="border-t divide-y" style={{ borderColor: 'rgba(255,255,255,0.05)', '--tw-divide-opacity': '1' } as any}>
                    {goal.plan.tasks.slice(0, 20).map((task, i) => (
                      <div key={task.id || i} className="px-5 py-3 flex items-start gap-3">
                        <div className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
                             style={{ background: 'rgba(124,58,237,0.15)', fontSize: '10px', color: '#A78BFA' }}>
                          {i + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-white/80 truncate">{task.title}</div>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="platform-badge text-[10px]">{task.platform}</span>
                            <span className="platform-badge text-[10px]">{task.content_type}</span>
                            {task.scheduled_at && (
                              <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.3)' }}>
                                {new Date(task.scheduled_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Agent Activity Feed — right 2 cols */}
          <div className="col-span-2">
            <div className="glass-panel h-full flex flex-col" style={{ maxHeight: 'calc(100vh - 200px)' }}>
              <div className="p-4 border-b flex items-center gap-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                <Bot size={15} className="text-primary-400" />
                <span className="text-sm font-semibold text-white">Agent Activity</span>
                {isActive && (
                  <div className="ml-auto flex gap-1">
                    <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
                  </div>
                )}
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {logs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-center py-8">
                    <div className="flex gap-1 mb-3">
                      <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
                    </div>
                    <p className="text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>Waiting for agent activity...</p>
                  </div>
                ) : (
                  logs.map((log, i) => {
                    const color = AGENT_COLORS[log.agent] || '#94A3B8'
                    const label = AGENT_LABELS[log.agent] || log.agent
                    return (
                      <div key={log.id || i} className="agent-log animate-slide-up" style={{ animationDelay: `${i * 20}ms` }}>
                        <div className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold"
                             style={{ background: `${color}20`, color, border: `1px solid ${color}30` }}>
                          {label[0]}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs font-semibold" style={{ color }}>{label}</span>
                            <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                              {new Date(log.created_at).toLocaleTimeString()}
                            </span>
                          </div>
                          <p className="text-xs leading-relaxed" style={{ color: 'rgba(255,255,255,0.6)' }}>
                            {log.thought}
                          </p>
                        </div>
                      </div>
                    )
                  })
                )}
                <div ref={logsEndRef} />
              </div>
            </div>
          </div>

        </div>
      </main>
    </div>
  )
}
