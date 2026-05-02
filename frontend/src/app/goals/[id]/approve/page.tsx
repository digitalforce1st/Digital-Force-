'use client'

import { useState, useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import {
  CheckCircle2, XCircle, ArrowLeft, Clock, AlertCircle,
  Calendar, Target, ChevronRight, RefreshCw, Zap
} from 'lucide-react'
import api, { Goal, CampaignTask } from '@/lib/api'
import Link from 'next/link'

const PLATFORM_EMOJI: Record<string, string> = {
  linkedin: '💼', facebook: '👥', twitter: '🐦',
  tiktok: '🎵', instagram: '📸', youtube: '▶️',
}
const CONTENT_TYPE_COLORS: Record<string, string> = {
  post: '#A78BFA', carousel: '#22D3EE', reel: '#F59E0B',
  story: '#34D399', thread: '#FCA5A5', video: '#FB923C',
}

export default function ApprovePage() {
  const pathname = usePathname()
  const router = useRouter()
  const goalId = pathname.split('/')[2] // extract from /goals/uuid/approve

  const [goal, setGoal] = useState<Goal | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<{ status: string; message: string } | null>(null)

  useEffect(() => {
    api.goals.get(goalId)
      .then(setGoal)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [goalId])

  const handleDecision = async (approved: boolean) => {
    setSubmitting(true)
    try {
      const res = await api.goals.approve(goalId, { approved, notes: notes || undefined })
      setResult(res)
      if (approved) {
        setTimeout(() => router.push(`/goals/${goalId}`), 2000)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
        </div>
      </main>
    </div>
  )

  if (!goal) return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
        <AlertCircle size={40} style={{ color: '#FCA5A5' }} />
        <div style={{ color: '#fff', fontWeight: 600 }}>Goal not found</div>
        <Link href="/goals" className="btn-ghost">← Back to Goals</Link>
      </main>
    </div>
  )

  const plan = goal.plan
  const tasks: CampaignTask[] = plan?.tasks || []

  if (result) return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '1.5rem' }}>
        {result.status === 'executing' ? (
          <>
            <div style={{ width: 72, height: 72, borderRadius: '50%',
              background: 'rgba(52,211,153,0.15)', border: '2px solid rgba(52,211,153,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CheckCircle2 size={36} style={{ color: '#34D399' }} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff', marginBottom: 8 }}>Plan Approved!</div>
              <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.9rem' }}>
                The agency is now executing your campaign. Redirecting...
              </div>
            </div>
          </>
        ) : (
          <>
            <div style={{ width: 72, height: 72, borderRadius: '50%',
              background: 'rgba(245,158,11,0.15)', border: '2px solid rgba(245,158,11,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <RefreshCw size={36} style={{ color: '#F59E0B' }} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff', marginBottom: 8 }}>Replanning...</div>
              <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.9rem' }}>{result.message}</div>
            </div>
            <Link href={`/goals/${goalId}`} className="btn-primary">View Goal</Link>
          </>
        )}
      </main>
    </div>
  )

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          {/* Back link */}
          <Link href={`/goals/${goalId}`} className="btn-ghost" style={{ marginBottom: '1.5rem', display: 'inline-flex' }}>
            <ArrowLeft size={14} /> Back to Goal
          </Link>

          {/* Alert banner */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '1rem 1.25rem',
            borderRadius: 14, marginBottom: '2rem',
            background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)',
          }}>
            <AlertCircle size={20} style={{ color: '#FCD34D', flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, color: '#FCD34D', fontSize: '0.9rem' }}>
                Your AI agency has a plan ready for your approval
              </div>
              <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem', marginTop: 2 }}>
                Review each task below. Approve to begin execution, or reject with feedback to replan.
              </div>
            </div>
          </div>

          {/* Goal header */}
          <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
              <div style={{ width: 44, height: 44, borderRadius: 12,
                background: 'rgba(124,58,237,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Target size={22} style={{ color: '#A78BFA' }} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: '1.1rem', color: '#fff', marginBottom: 6 }}>{goal.title}</div>
                <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.875rem', lineHeight: 1.6 }}>{goal.description}</div>
                <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                  {goal.platforms.map(p => (
                    <span key={p} style={{
                      fontSize: '0.78rem', padding: '0.2rem 0.6rem', borderRadius: 6,
                      background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.6)',
                    }}>{PLATFORM_EMOJI[p] || '📱'} {p}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Plan summary */}
          {plan && (
            <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.25rem' }}>
              <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Zap size={16} style={{ color: '#A78BFA' }} /> Campaign Plan
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                {[
                  { label: 'Campaign Name', value: plan.campaign_name || goal.title },
                  { label: 'Duration', value: `${plan.duration_days || 7} days` },
                  { label: 'Total Tasks', value: tasks.length },
                ].map(item => (
                  <div key={item.label} style={{ textAlign: 'center', padding: '0.75rem',
                    background: 'rgba(255,255,255,0.03)', borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff' }}>{item.value}</div>
                    <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', marginTop: 4 }}>{item.label}</div>
                  </div>
                ))}
              </div>
              {plan.campaign_summary && (
                <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: '0.875rem', lineHeight: 1.7,
                  padding: '0.875rem', background: 'rgba(255,255,255,0.03)', borderRadius: 10 }}>
                  {plan.campaign_summary}
                </div>
              )}
            </div>
          )}

          {/* Tasks list */}
          {tasks.length > 0 && (
            <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
              <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Calendar size={16} style={{ color: '#22D3EE' }} /> Planned Tasks ({tasks.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {tasks.map((task, i) => (
                  <div key={task.id || i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 12, padding: '0.875rem',
                    borderRadius: 12, background: 'rgba(255,255,255,0.03)',
                    border: '1px solid rgba(255,255,255,0.06)',
                  }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                      background: `${CONTENT_TYPE_COLORS[task.content_type] || '#A78BFA'}15`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '0.85rem',
                    }}>
                      {PLATFORM_EMOJI[task.platform] || '📱'}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, fontSize: '0.875rem', color: '#fff' }}>{task.title}</span>
                        <span style={{
                          fontSize: '0.7rem', padding: '0.15rem 0.5rem', borderRadius: 6,
                          background: `${CONTENT_TYPE_COLORS[task.content_type] || '#A78BFA'}20`,
                          color: CONTENT_TYPE_COLORS[task.content_type] || '#A78BFA',
                          textTransform: 'capitalize',
                        }}>{task.content_type}</span>
                      </div>
                      {task.content_brief && (
                        <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.8rem', lineHeight: 1.5 }}>
                          {task.content_brief}
                        </div>
                      )}
                      {task.scheduled_at && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 6,
                          color: 'rgba(255,255,255,0.3)', fontSize: '0.75rem' }}>
                          <Clock size={11} />
                          {new Date(task.scheduled_at).toLocaleDateString('en-US', {
                            weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                          })}
                        </div>
                      )}
                    </div>
                    <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.25)', flexShrink: 0 }}>#{i + 1}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Feedback + Decision */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1rem' }}>Your Decision</div>

            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.45)', display: 'block', marginBottom: 8 }}>
                Notes / Feedback (optional)
              </label>
              <textarea
                id="approval-notes"
                value={notes}
                onChange={e => setNotes(e.target.value)}
                rows={3}
                placeholder="e.g. 'Remove TikTok posts, focus more on educational content, increase posting frequency'"
                style={{
                  width: '100%', padding: '0.75rem', borderRadius: 10,
                  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)',
                  color: '#fff', fontSize: '0.875rem', outline: 'none',
                  resize: 'none', boxSizing: 'border-box', fontFamily: 'inherit', lineHeight: 1.6,
                }}
              />
            </div>

            {error && (
              <div style={{
                display: 'flex', gap: 8, alignItems: 'center', marginBottom: '1rem',
                padding: '0.65rem 1rem', borderRadius: 10,
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                color: '#FCA5A5', fontSize: '0.85rem',
              }}>
                <AlertCircle size={14} /> {error}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10 }}>
              <button id="approve-plan" onClick={() => handleDecision(true)} disabled={submitting} className="btn-primary"
                style={{ flex: 1, justifyContent: 'center', opacity: submitting ? 0.7 : 1 }}>
                {submitting ? <RefreshCw size={15} /> : <CheckCircle2 size={15} />}
                Approve & Execute
              </button>
              <button id="reject-plan" onClick={() => handleDecision(false)} disabled={submitting} className="btn-danger"
                style={{ flex: 1, justifyContent: 'center', opacity: submitting ? 0.7 : 1 }}>
                {submitting ? <RefreshCw size={15} /> : <XCircle size={15} />}
                Reject & Replan
              </button>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.25)', textAlign: 'center', marginTop: '0.75rem' }}>
              Approve to begin execution · Reject with feedback to replan
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
