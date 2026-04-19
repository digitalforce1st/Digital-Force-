'use client'

import { useState, useEffect, useRef, useCallback, KeyboardEvent } from 'react'
import Sidebar from '@/components/Sidebar'
import {
  Send, Trash2, Bot, User, Zap, MessageSquare, Plus, X,
  Image as ImageIcon, Clock, ChevronDown, ChevronRight,
  Brain, Wrench, Eye, Loader2, Terminal, Sparkles,
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { getToken } from '@/lib/auth'
import api, { MediaAsset } from '@/lib/api'
import AssetSelector from '@/components/chat/AssetSelector'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ─── Types ─────────────────────────────────────────────────────────────────────

type StepType = 'thinking' | 'action' | 'observation'

interface ReasoningStep {
  id: string
  type: StepType
  content: string
  tool?: string
  args_preview?: string
  isOpen: boolean
  isLive: boolean // currently streaming into this step
}

interface Message {
  id: string
  role: 'user' | 'assistant' | 'agent'
  agentName?: string
  content: string
  isStreaming: boolean
  steps: ReasoningStep[]
  created_at: string
}

// ─── Agent visual config ────────────────────────────────────────────────────────

const AGENT_CONFIG: Record<string, { initials: string; label: string; color: string }> = {
  orchestrator:       { initials: 'OR', label: 'Orchestrator',     color: '#F59E0B' },
  researcher:         { initials: 'RE', label: 'Researcher',       color: '#3B82F6' },
  strategist:         { initials: 'ST', label: 'Strategist',       color: '#8B5CF6' },
  content_director:   { initials: 'CD', label: 'Content Director', color: '#EC4899' },
  publisher:          { initials: 'PB', label: 'Publisher',        color: '#10B981' },
  skillforge:         { initials: 'SF', label: 'SkillForge',       color: '#F97316' },
  monitor:            { initials: 'MN', label: 'Monitor',          color: '#00A3FF' },
  'executive - hub':  { initials: 'EX', label: 'Digital Force',    color: '#00A3FF' },
}

const STEP_CONFIG: Record<StepType, { icon: React.ElementType; label: string; color: string; bg: string; border: string }> = {
  thinking:    { icon: Brain,    label: 'Thinking',    color: '#A78BFA', bg: 'rgba(167,139,250,0.05)', border: 'rgba(167,139,250,0.15)' },
  action:      { icon: Wrench,   label: 'Working',     color: '#00A3FF', bg: 'rgba(0,163,255,0.05)',   border: 'rgba(0,163,255,0.18)' },
  observation: { icon: Eye,      label: 'Observed',    color: '#34D399', bg: 'rgba(52,211,153,0.05)',  border: 'rgba(52,211,153,0.15)' },
}

const SUGGESTED_PROMPTS = [
  'Deploy a 2-week LinkedIn campaign for a SaaS product launch',
  'What tasks are active and how are they performing?',
  'Search the web for the latest AI industry trends and summarize',
  'Analyze our knowledge base and suggest a content strategy',
  'Which platform is generating the highest engagement rate?',
]

// ─── Convert DB history record → Message ────────────────────────────────────────

function historyToMessage(h: { id: string; role: string; content: string; agent_name?: string; created_at: string }): Message {
  return {
    id: h.id,
    role: h.role as 'user' | 'assistant' | 'agent',
    agentName: h.agent_name || undefined,
    content: h.content,
    isStreaming: false,
    steps: [],
    created_at: h.created_at,
  }
}

// ─── Reasoning Step Component ───────────────────────────────────────────────────

function ReasoningBlock({ step, onToggle }: { step: ReasoningStep; onToggle: () => void }) {
  const cfg = STEP_CONFIG[step.type]
  const Icon = cfg.icon

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        border: `1px solid ${cfg.border}`,
        borderRadius: 10,
        background: cfg.bg,
        overflow: 'hidden',
        marginBottom: 6,
      }}
    >
      {/* Header row */}
      <button
        onClick={onToggle}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          padding: '0.5rem 0.75rem', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <Icon size={13} style={{ color: cfg.color, flexShrink: 0 }} />
        <span style={{ fontSize: '0.72rem', fontWeight: 700, color: cfg.color, letterSpacing: '0.06em', flexShrink: 0 }}>
          {cfg.label}
          {step.tool && (
            <span style={{ color: 'rgba(255,255,255,0.4)', fontWeight: 400, marginLeft: 6, fontFamily: 'monospace' }}>
              {step.tool}
            </span>
          )}
        </span>
        {step.isLive && (
          <span style={{ marginLeft: 4, display: 'flex', gap: 2, alignItems: 'center' }}>
            {[0,1,2].map(i => (
              <span key={i} style={{
                width: 4, height: 4, borderRadius: '50%', background: cfg.color,
                animation: 'pulse 1.2s infinite', animationDelay: `${i * 0.2}s`,
                display: 'inline-block',
              }} />
            ))}
          </span>
        )}
        <span style={{ marginLeft: 'auto', color: 'rgba(255,255,255,0.25)', display: 'flex' }}>
          {step.isOpen
            ? <ChevronDown size={13} />
            : <ChevronRight size={13} />
          }
        </span>
      </button>

      {/* Body */}
      <AnimatePresence initial={false}>
        {step.isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
          >
            <div style={{
              padding: '0 0.75rem 0.65rem',
              borderTop: `1px solid ${cfg.border}`,
            }}>
              {/* Args preview for actions */}
              {step.type === 'action' && step.args_preview && (
                <div style={{
                  fontFamily: 'JetBrains Mono, Fira Code, monospace',
                  fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)',
                  background: 'rgba(0,0,0,0.2)',
                  padding: '0.35rem 0.6rem', borderRadius: 6,
                  marginTop: '0.4rem', marginBottom: '0.4rem',
                  overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                }}>
                  {step.args_preview}
                </div>
              )}
              <p style={{
                margin: 0,
                fontSize: '0.8rem',
                lineHeight: 1.65,
                color: 'rgba(255,255,255,0.6)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                paddingTop: step.type === 'action' && step.args_preview ? 0 : '0.4rem',
              }}>
                {step.content}
                {step.isLive && <span style={{ color: cfg.color, marginLeft: 2 }}>▋</span>}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ─── Main Chat Component ────────────────────────────────────────────────────────

export default function ChatPage() {
  const [messages, setMessages]           = useState<Message[]>([])
  const [input, setInput]                 = useState('')
  const [loading, setLoading]             = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [lastPollTime, setLastPollTime]   = useState<string | null>(null)
  const [agentsActive, setAgentsActive]   = useState(false)
  const [currentActivity, setCurrentActivity] = useState<string | null>(null)
  const [showAssetSelector, setShowAssetSelector] = useState(false)
  const [attachedMedia, setAttachedMedia] = useState<MediaAsset[]>([])

  const bottomRef   = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const currentMsgIdRef = useRef<string | null>(null)

  const handleSelectAsset = useCallback((asset: MediaAsset) => {
    setAttachedMedia(prev => prev.find(a => a.id === asset.id) ? prev : [...prev, asset])
  }, [])

  // ── Load history ────────────────────────────────────────────────────────────
  useEffect(() => {
    api.chat.history()
      .then(history => {
        if (history.length > 0) {
          setMessages(history.map(historyToMessage))
          setLastPollTime(history[history.length - 1].created_at)
        }
        setHistoryLoaded(true)
      })
      .catch(() => setHistoryLoaded(true))
  }, [])

  // ── Auto-scroll ─────────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Background agent polling ────────────────────────────────────────────────
  useEffect(() => {
    if (!historyLoaded) return
    const poll = async () => {
      try {
        const data = await api.chat.updates(lastPollTime || undefined)
        setAgentsActive(data.agents_active)
        setCurrentActivity(data.current_activity ?? null)
        if (data.messages?.length > 0) {
          setMessages(prev => {
            const ids = new Set(prev.map(m => m.id))
            const fresh = data.messages.filter(u => !ids.has(u.id)).map(historyToMessage)
            return fresh.length > 0 ? [...prev, ...fresh] : prev
          })
          setLastPollTime(data.messages[data.messages.length - 1].created_at)
        }
      } catch { /* silent */ }
    }
    poll()
    const t = setInterval(poll, 12_000)
    return () => clearInterval(t)
  }, [historyLoaded])

  // ── Toggle a reasoning step ─────────────────────────────────────────────────
  const toggleStep = useCallback((msgId: string, stepId: string) => {
    setMessages(prev => prev.map(m =>
      m.id !== msgId ? m : {
        ...m,
        steps: m.steps.map(s => s.id === stepId ? { ...s, isOpen: !s.isOpen } : s)
      }
    ))
  }, [])

  // ── Send a message ──────────────────────────────────────────────────────────
  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text || input).trim()
    if (!msg || loading) return

    setInput('')
    setLoading(true)
    setAttachedMedia([])

    const now = new Date().toISOString()
    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: msg,
      isStreaming: false,
      steps: [],
      created_at: now,
    }

    const assistantId = `a-${Date.now()}`
    currentMsgIdRef.current = assistantId
    const assistantMsg: Message = {
      id: assistantId,
      role: 'agent',
      agentName: 'executive - hub',
      content: '',
      isStreaming: true,
      steps: [],
      created_at: now,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])

    try {
      const token = getToken()
      const response = await fetch(`${BASE}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: msg,
          context: attachedMedia.length > 0 ? { attached_media: attachedMedia.map(a => a.id) } : {}
        }),
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader  = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let activeStepId: string | null = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            const msgId = currentMsgIdRef.current!

            if (event.type === 'done') {
              // Mark all live steps as done
              setMessages(prev => prev.map(m =>
                m.id !== msgId ? m : {
                  ...m,
                  isStreaming: false,
                  steps: m.steps.map(s => ({ ...s, isLive: false }))
                }
              ))
              break
            }

            if (event.type === 'thinking' || event.type === 'action' || event.type === 'observation') {
              const stepId = `step-${Date.now()}-${Math.random()}`
              activeStepId = stepId
              const step: ReasoningStep = {
                id: stepId,
                type: event.type as StepType,
                content: event.content || '',
                tool: event.tool,
                args_preview: event.args_preview,
                isOpen: event.type === 'action', // actions open by default
                isLive: false,
              }
              setMessages(prev => prev.map(m =>
                m.id !== msgId ? m : {
                  ...m,
                  steps: [
                    ...m.steps.map(s => ({ ...s, isLive: false })),
                    step,
                  ]
                }
              ))
            }

            else if (event.type === 'token') {
              // Stream final answer tokens
              activeStepId = null
              setMessages(prev => prev.map(m =>
                m.id !== msgId ? m : {
                  ...m,
                  content: m.content + (event.content || ''),
                  isStreaming: true,
                  steps: m.steps.map(s => ({ ...s, isLive: false }))
                }
              ))
            }

            else if (event.type === 'error') {
              setMessages(prev => prev.map(m =>
                m.id !== msgId ? m : {
                  ...m,
                  content: `⚠ ${event.content}`,
                  isStreaming: false,
                  steps: m.steps.map(s => ({ ...s, isLive: false }))
                }
              ))
            }

          } catch { /* skip malformed */ }
        }
      }

    } catch (err) {
      const msgId = currentMsgIdRef.current!
      setMessages(prev => prev.map(m =>
        m.id !== msgId ? m : { ...m, content: '⚠ Connection error. Please try again.', isStreaming: false }
      ))
    } finally {
      setMessages(prev => prev.map(m =>
        m.id === currentMsgIdRef.current ? { ...m, isStreaming: false, steps: m.steps.map(s => ({ ...s, isLive: false })) } : m
      ))
      setLoading(false)
      setLastPollTime(new Date().toISOString())
    }
  }, [input, loading, attachedMedia])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearHistory = async () => {
    await api.chat.clearHistory()
    setMessages([])
    setLastPollTime(null)
  }

  const formatTime = (iso: string) => {
    const s = iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`
    return new Date(s).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  // ── Render single message ───────────────────────────────────────────────────
  const renderMessage = (msg: Message) => {
    const isUser  = msg.role === 'user'
    const agentCfg = !isUser
      ? (msg.agentName ? AGENT_CONFIG[msg.agentName] : null) ?? AGENT_CONFIG['executive - hub']
      : null

    return (
      <motion.div
        key={msg.id}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: 10 }}
      >
        {/* Avatar */}
        <div style={{
          width: 34, height: 34, borderRadius: 10, flexShrink: 0,
          background: isUser
            ? 'rgba(0,163,255,0.12)'
            : agentCfg ? `${agentCfg.color}1A` : 'rgba(0,163,255,0.12)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: isUser
            ? '1px solid rgba(0,163,255,0.25)'
            : agentCfg ? `1px solid ${agentCfg.color}33` : '1px solid rgba(0,163,255,0.25)',
          fontSize: '0.6rem', fontWeight: 800, marginTop: 2,
        }}>
          {isUser
            ? <User size={15} style={{ color: '#33BAFF' }} />
            : agentCfg
              ? <span style={{ color: agentCfg.color, fontSize: '0.6rem', fontWeight: 900 }}>{agentCfg.initials}</span>
              : <Bot size={15} color="white" />
          }
        </div>

        {/* Content column */}
        <div style={{ maxWidth: '78%', minWidth: 60, display: 'flex', flexDirection: 'column', gap: 4 }}>

          {/* Agent badge */}
          {!isUser && agentCfg && (
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.06em',
              color: agentCfg.color, paddingBottom: 2,
            }}>
              <span style={{
                width: 5, height: 5, borderRadius: '50%', background: agentCfg.color,
                boxShadow: `0 0 8px ${agentCfg.color}`,
                animation: msg.isStreaming ? 'pulse 1.5s infinite' : 'none',
              }} />
              {agentCfg.label.toUpperCase()}
            </div>
          )}

          {/* Reasoning Steps */}
          {msg.steps.length > 0 && (
            <div style={{ marginBottom: 4 }}>
              {msg.steps.map(step => (
                <ReasoningBlock
                  key={step.id}
                  step={step}
                  onToggle={() => toggleStep(msg.id, step.id)}
                />
              ))}
            </div>
          )}

          {/* Final answer bubble */}
          {(msg.content || msg.isStreaming) && (
            <div style={{
              padding: '0.875rem 1.125rem', borderRadius: 14,
              background: isUser
                ? 'linear-gradient(135deg, rgba(0,163,255,0.2), rgba(0,97,153,0.15))'
                : 'rgba(255,255,255,0.04)',
              border: isUser
                ? '1px solid rgba(0,163,255,0.25)'
                : agentCfg ? `1px solid ${agentCfg.color}20` : '1px solid rgba(255,255,255,0.07)',
              color: '#F8FAFC', fontSize: '0.9rem', lineHeight: 1.7,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>
              {msg.content}
              {msg.isStreaming && !msg.content && (
                <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                  {[0,1,2].map(i => (
                    <span key={i} className="thinking-dot" style={{ width: 6, height: 6, animationDelay: `${i * 0.15}s` }} />
                  ))}
                </span>
              )}
              {msg.isStreaming && msg.content && (
                <span style={{ display: 'inline-block', width: 2, height: '1em', background: '#00A3FF', marginLeft: 2, verticalAlign: 'text-bottom', animation: 'pulse 1s infinite' }} />
              )}
            </div>
          )}

          {/* Timestamp */}
          <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.2)', textAlign: isUser ? 'right' : 'left', marginTop: 2 }}>
            {formatTime(msg.created_at)}
          </div>
        </div>
      </motion.div>
    )
  }

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#080B12' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* ── Header ── */}
        <div style={{
          padding: '1rem 1.5rem',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'rgba(8,11,18,0.8)', backdropFilter: 'blur(10px)',
          flexShrink: 0, position: 'sticky', top: 0, zIndex: 20,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10,
              background: 'linear-gradient(135deg, #00A3FF, #006199)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 24px rgba(0,163,255,0.4)',
              border: '1px solid rgba(255,255,255,0.1)',
            }}>
              <Zap size={18} color="white" />
            </div>
            <div>
              <div style={{ fontWeight: 800, fontSize: '0.95rem', letterSpacing: '-0.02em', background: 'linear-gradient(180deg,#FFF 0%,#94BFDB 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                Agentic Hub
              </div>
              <div style={{ fontSize: '0.62rem', color: '#475569', fontWeight: 700, letterSpacing: '0.07em', marginTop: 1 }}>
                DIGITAL FORCE COMMAND INTERFACE
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Live activity pill */}
            <AnimatePresence>
              {agentsActive && currentActivity && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    background: 'rgba(0,163,255,0.06)', border: '1px solid rgba(0,163,255,0.15)',
                    borderRadius: 20, padding: '5px 12px',
                    fontSize: '0.7rem', color: '#33BAFF', fontWeight: 600,
                    maxWidth: 360, overflow: 'hidden',
                  }}
                >
                  <span className="thinking-dot" style={{ flexShrink: 0, width: 6, height: 6, background: '#00A3FF' }} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {currentActivity.length > 55 ? currentActivity.slice(0, 55) + '...' : currentActivity}
                  </span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Session controls */}
            {messages.length > 0 && (
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={clearHistory} title="Clear History" style={iconBtn('#EF4444')}>
                  <Trash2 size={15} />
                </button>
                <button onClick={() => setMessages([])} title="New Session" style={iconBtn('#00A3FF')}>
                  <Plus size={15} />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* ── Messages ── */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '2rem 1.5rem' }}>
          {historyLoaded && messages.length === 0 ? (
            /* ── Empty state ── */
            <div style={{ maxWidth: 600, margin: '4rem auto', textAlign: 'center' }}>
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.1 }}
                style={{
                  width: 80, height: 80, borderRadius: 22, margin: '0 auto 1.75rem',
                  background: 'radial-gradient(circle, rgba(0,163,255,0.12) 0%, rgba(0,163,255,0.04) 100%)',
                  border: '1px solid rgba(0,163,255,0.2)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 0 60px rgba(0,163,255,0.12)',
                }}
              >
                <Sparkles size={34} style={{ color: '#33BAFF' }} />
              </motion.div>
              <motion.h2
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                style={{ fontSize: '1.4rem', fontWeight: 800, color: '#F8FAFC', marginBottom: 8, letterSpacing: '-0.02em' }}
              >
                Initialize Command
              </motion.h2>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                style={{ color: '#64748B', fontSize: '0.9rem', lineHeight: 1.7, marginBottom: '2.5rem' }}
              >
                Brief the autonomous agency. Watch it reason, act, and observe — showing you every step of its thinking.
              </motion.p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {SUGGESTED_PROMPTS.map((p, i) => (
                  <motion.button
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.35 + i * 0.07 }}
                    onClick={() => sendMessage(p)}
                    style={{
                      padding: '0.8rem 1.1rem', borderRadius: 10, textAlign: 'left',
                      background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)',
                      color: '#64748B', fontSize: '0.85rem', cursor: 'pointer',
                      transition: 'all 0.2s', fontWeight: 400, width: '100%',
                    }}
                    onMouseEnter={e => {
                      const el = e.currentTarget
                      el.style.background = 'rgba(0,163,255,0.07)'
                      el.style.borderColor = 'rgba(0,163,255,0.22)'
                      el.style.color = '#E2E8F0'
                    }}
                    onMouseLeave={e => {
                      const el = e.currentTarget
                      el.style.background = 'rgba(255,255,255,0.02)'
                      el.style.borderColor = 'rgba(255,255,255,0.05)'
                      el.style.color = '#64748B'
                    }}
                  >
                    {p}
                  </motion.button>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ maxWidth: 840, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              {messages.map(renderMessage)}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* ── Input ── */}
        <div style={{
          padding: '1rem 1.5rem 1.25rem',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          background: 'rgba(8,11,18,0.85)', backdropFilter: 'blur(16px)',
          flexShrink: 0,
        }}>
          <div style={{ maxWidth: 840, margin: '0 auto' }}>

            {/* Attached media */}
            {attachedMedia.length > 0 && (
              <div style={{ display: 'flex', gap: 8, marginBottom: '0.75rem', flexWrap: 'wrap' }}>
                {attachedMedia.map(a => (
                  <div key={a.id} style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    background: 'rgba(0,163,255,0.08)', border: '1px solid rgba(0,163,255,0.2)',
                    borderRadius: 8, padding: '0.35rem 0.6rem',
                  }}>
                    {a.asset_type === 'image' && a.public_url
                      ? <img src={`${BASE}${a.public_url}`} style={{ width: 22, height: 22, borderRadius: 4, objectFit: 'cover' }} alt="" />
                      : <ImageIcon size={14} color="#00A3FF" />
                    }
                    <span style={{ fontSize: '0.72rem', color: '#E2E8F0', maxWidth: 100, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.filename}</span>
                    <button onClick={() => setAttachedMedia(prev => prev.filter(m => m.id !== a.id))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94A3B8', display: 'flex', padding: 0 }}>
                      <X size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Input row */}
            <div style={{
              display: 'flex', gap: 8, alignItems: 'flex-end',
              background: 'rgba(15,23,42,0.7)',
              border: `1px solid ${loading ? 'rgba(0,163,255,0.35)' : 'rgba(255,255,255,0.06)'}`,
              borderRadius: 16, padding: '0.5rem',
              backdropFilter: 'blur(12px)',
              transition: 'border-color 0.2s, box-shadow 0.2s',
              boxShadow: loading ? '0 0 30px rgba(0,163,255,0.08)' : 'none',
              position: 'relative',
            }}>
              {showAssetSelector && (
                <AssetSelector onSelect={handleSelectAsset} onClose={() => setShowAssetSelector(false)} />
              )}
              <button
                onClick={() => setShowAssetSelector(v => !v)}
                style={{
                  width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                  background: showAssetSelector ? 'rgba(0,163,255,0.12)' : 'rgba(255,255,255,0.03)',
                  border: showAssetSelector ? '1px solid rgba(0,163,255,0.3)' : '1px solid rgba(255,255,255,0.05)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: showAssetSelector ? '#33BAFF' : '#64748B',
                  transition: 'all 0.2s', marginBottom: 2,
                }}
              >
                <Plus size={17} />
              </button>
              <textarea
                ref={textareaRef}
                id="chat-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={loading ? 'Agency is processing...' : 'Brief the agency... (Enter to transmit)'}
                disabled={loading}
                rows={1}
                style={{
                  flex: 1, background: 'none', border: 'none', outline: 'none',
                  color: '#F8FAFC', fontSize: '0.9rem', lineHeight: 1.55,
                  resize: 'none', maxHeight: 140, fontFamily: 'inherit',
                  opacity: loading ? 0.5 : 1, marginBottom: 6,
                  scrollbarWidth: 'none',
                }}
                onInput={e => {
                  const t = e.target as HTMLTextAreaElement
                  t.style.height = 'auto'
                  t.style.height = Math.min(t.scrollHeight, 140) + 'px'
                }}
              />
              <button
                id="send-chat"
                onClick={() => sendMessage()}
                disabled={loading || !input.trim()}
                style={{
                  width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                  background: input.trim() && !loading
                    ? 'linear-gradient(135deg, #00A3FF, #006199)'
                    : 'rgba(255,255,255,0.03)',
                  border: input.trim() && !loading ? '1px solid rgba(255,255,255,0.15)' : '1px solid rgba(255,255,255,0.04)',
                  cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.25s',
                  boxShadow: input.trim() && !loading ? '0 0 24px rgba(0,163,255,0.5)' : 'none',
                  marginBottom: 2,
                }}
              >
                {loading
                  ? <Loader2 size={16} color="#64748B" style={{ animation: 'spin 1s linear infinite' }} />
                  : <Send size={16} color={input.trim() ? 'white' : '#334155'} />
                }
              </button>
            </div>

            <div style={{ fontSize: '0.65rem', color: '#1E293B', textAlign: 'center', marginTop: 8, fontWeight: 600, letterSpacing: '0.05em' }}>
              DIGITAL FORCE — AGENTIC AI PLATFORM
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Utilities ──────────────────────────────────────────────────────────────────
function iconBtn(color: string): React.CSSProperties {
  return {
    width: 34, height: 34, borderRadius: 8,
    background: 'rgba(255,255,255,0.03)',
    border: `1px solid ${color}22`,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color, cursor: 'pointer', transition: 'all 0.2s',
  }
}
