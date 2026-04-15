'use client'

import { useState, useEffect, useRef, KeyboardEvent } from 'react'
import Sidebar from '@/components/Sidebar'
import { Send, Trash2, Bot, User, Zap, MessageSquare } from 'lucide-react'
import { getToken } from '@/lib/auth'
import api from '@/lib/api'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  chunks?: { type: string; content: string }[]
  isStreaming?: boolean
  created_at: string
}

const AGENT_COLORS: Record<string, string> = {
  thinking: 'rgba(255,255,255,0.3)',
  action: '#22D3EE',
  message: '#fff',
  error: '#FCA5A5',
}

const SUGGESTED_PROMPTS = [
  "Create a 2-week LinkedIn campaign for my SaaS product",
  "What campaigns are currently active and how are they performing?",
  "Show me what's scheduled for this week",
  "Replan my top campaign with more video content",
  "Which platform is delivering the best results?",
]

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Load chat history on mount
  useEffect(() => {
    api.chat.history()
      .then(history => {
        if (history.length > 0) {
          setMessages(history.map(h => ({
            id: h.id,
            role: h.role,
            content: h.content,
            created_at: h.created_at,
          })))
        }
        setHistoryLoaded(true)
      })
      .catch(() => setHistoryLoaded(true))
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text?: string) => {
    const msg = (text || input).trim()
    if (!msg || loading) return

    setInput('')
    setLoading(true)

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: msg,
      created_at: new Date().toISOString(),
    }

    const assistantMsg: Message = {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: '',
      chunks: [],
      isStreaming: true,
      created_at: new Date().toISOString(),
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
        body: JSON.stringify({ message: msg, context: {} }),
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const chunk = JSON.parse(line.slice(6))

            if (chunk.type === 'done') break

            setMessages(prev => prev.map(m => {
              if (m.id !== assistantMsg.id) return m
              const newChunks = [...(m.chunks || []), chunk]
              const messageText = newChunks
                .filter(c => c.type === 'message')
                .map(c => c.content)
                .join('')
              return {
                ...m,
                content: messageText,
                chunks: newChunks,
                isStreaming: chunk.type !== 'done',
              }
            }))
          } catch { /* skip malformed chunks */ }
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === assistantMsg.id
          ? { ...m, content: 'Connection error. Please check your settings and try again.', isStreaming: false }
          : m
      ))
    } finally {
      setMessages(prev => prev.map(m =>
        m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
      ))
      setLoading(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearHistory = async () => {
    await api.chat.clearHistory()
    setMessages([])
  }

  const formatTime = (iso: string) => {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{
          padding: '1rem 1.5rem',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'rgba(255,255,255,0.02)', backdropFilter: 'blur(10px)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'linear-gradient(135deg, #7C3AED, #4F46E5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 20px rgba(124,58,237,0.3)',
            }}>
              <Zap size={18} color="white" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', color: '#fff' }}>ASMIA</div>
              <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)' }}>
                Autonomous Social Media Intelligence Agency
              </div>
            </div>
          </div>
          {messages.length > 0 && (
            <button onClick={clearHistory} className="btn-ghost" style={{ fontSize: '0.8rem', gap: 6 }}>
              <Trash2 size={14} /> Clear history
            </button>
          )}
        </div>

        {/* Messages area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem' }}>
          {historyLoaded && messages.length === 0 ? (
            /* Empty state */
            <div style={{ maxWidth: 600, margin: '3rem auto', textAlign: 'center' }}>
              <div style={{
                width: 72, height: 72, borderRadius: 20,
                background: 'rgba(124,58,237,0.1)',
                border: '1px solid rgba(124,58,237,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 1.5rem',
              }}>
                <MessageSquare size={32} style={{ color: '#A78BFA' }} />
              </div>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 700, color: '#fff', marginBottom: 8 }}>
                Talk to your agency
              </h2>
              <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.9rem', marginBottom: '2rem', lineHeight: 1.6 }}>
                Brief ASMIA in plain English. Create campaigns, check performance, adjust strategies — all through natural conversation.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {SUGGESTED_PROMPTS.map((p, i) => (
                  <button key={i} onClick={() => sendMessage(p)}
                    style={{
                      padding: '0.75rem 1rem', borderRadius: 12, textAlign: 'left',
                      background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
                      color: 'rgba(255,255,255,0.65)', fontSize: '0.875rem', cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = 'rgba(124,58,237,0.12)'
                      e.currentTarget.style.borderColor = 'rgba(124,58,237,0.25)'
                      e.currentTarget.style.color = '#fff'
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
                      e.currentTarget.style.borderColor = 'rgba(255,255,255,0.07)'
                      e.currentTarget.style.color = 'rgba(255,255,255,0.65)'
                    }}>
                    "{p}"
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ maxWidth: 820, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {messages.map(msg => (
                <div key={msg.id} style={{
                  display: 'flex',
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                  alignItems: 'flex-start', gap: 12,
                }}>
                  {/* Avatar */}
                  <div style={{
                    width: 32, height: 32, borderRadius: 10, flexShrink: 0,
                    background: msg.role === 'user'
                      ? 'rgba(167,139,250,0.15)'
                      : 'linear-gradient(135deg, #7C3AED, #4F46E5)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    border: msg.role === 'user' ? '1px solid rgba(167,139,250,0.25)' : 'none',
                  }}>
                    {msg.role === 'user'
                      ? <User size={15} style={{ color: '#A78BFA' }} />
                      : <Bot size={15} color="white" />
                    }
                  </div>

                  {/* Bubble */}
                  <div style={{ maxWidth: '75%', minWidth: 60 }}>
                    {msg.role === 'assistant' && msg.chunks && msg.chunks.length > 0 ? (
                      <div>
                        {/* Thinking / action chunks (collapsible) */}
                        {msg.chunks.filter(c => c.type === 'thinking' || c.type === 'action').length > 0 && (
                          <div style={{ marginBottom: 8 }}>
                            {msg.chunks.filter(c => c.type === 'thinking' || c.type === 'action').map((c, i) => (
                              <div key={i} style={{
                                fontSize: '0.75rem', padding: '0.3rem 0.6rem',
                                borderRadius: 6, marginBottom: 4, display: 'inline-flex',
                                alignItems: 'center', gap: 6,
                                background: c.type === 'action'
                                  ? 'rgba(34,211,238,0.08)' : 'rgba(255,255,255,0.04)',
                                border: `1px solid ${c.type === 'action' ? 'rgba(34,211,238,0.2)' : 'rgba(255,255,255,0.07)'}`,
                                color: AGENT_COLORS[c.type],
                              }}>
                                {c.type === 'action' && '⚙️ '}
                                {c.type === 'thinking' && '💭 '}
                                {c.content}
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Main message */}
                        {msg.content && (
                          <div className="glass-panel" style={{
                            padding: '0.875rem 1.125rem',
                            color: '#fff', fontSize: '0.9rem', lineHeight: 1.65,
                            whiteSpace: 'pre-wrap',
                          }}>
                            {msg.content}
                            {msg.isStreaming && (
                              <span style={{ display: 'inline-flex', gap: 3, marginLeft: 6, verticalAlign: 'middle' }}>
                                <span className="thinking-dot" style={{ width: 5, height: 5 }} />
                                <span className="thinking-dot" style={{ width: 5, height: 5 }} />
                                <span className="thinking-dot" style={{ width: 5, height: 5 }} />
                              </span>
                            )}
                          </div>
                        )}
                        {/* Streaming placeholder */}
                        {msg.isStreaming && !msg.content && (
                          <div className="glass-panel" style={{ padding: '0.875rem 1.125rem' }}>
                            <span style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                              <span className="thinking-dot" />
                              <span className="thinking-dot" />
                              <span className="thinking-dot" />
                            </span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div style={{
                        padding: '0.75rem 1rem',
                        borderRadius: 14,
                        background: msg.role === 'user'
                          ? 'linear-gradient(135deg, rgba(124,58,237,0.3), rgba(79,70,229,0.25))'
                          : 'rgba(255,255,255,0.05)',
                        border: `1px solid ${msg.role === 'user' ? 'rgba(124,58,237,0.3)' : 'rgba(255,255,255,0.07)'}`,
                        color: '#fff', fontSize: '0.9rem', lineHeight: 1.65, whiteSpace: 'pre-wrap',
                      }}>
                        {msg.content || (
                          <span style={{ display: 'flex', gap: 4 }}>
                            <span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" />
                          </span>
                        )}
                      </div>
                    )}
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.25)', marginTop: 4,
                      textAlign: msg.role === 'user' ? 'right' : 'left' }}>
                      {formatTime(msg.created_at)}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div style={{
          padding: '1rem 1.5rem 1.25rem',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          background: 'rgba(255,255,255,0.02)',
          flexShrink: 0,
        }}>
          <div style={{ maxWidth: 820, margin: '0 auto' }}>
            <div style={{
              display: 'flex', gap: 10, alignItems: 'flex-end',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 16, padding: '0.5rem 0.5rem 0.5rem 1rem',
            }}>
              <textarea
                ref={textareaRef}
                id="chat-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Brief the agency... (Enter to send, Shift+Enter for newline)"
                disabled={loading}
                rows={1}
                style={{
                  flex: 1, background: 'none', border: 'none', outline: 'none',
                  color: '#fff', fontSize: '0.9rem', lineHeight: 1.5, resize: 'none',
                  minHeight: 24, maxHeight: 120, fontFamily: 'inherit',
                  opacity: loading ? 0.6 : 1,
                }}
                onInput={e => {
                  const t = e.target as HTMLTextAreaElement
                  t.style.height = 'auto'
                  t.style.height = Math.min(t.scrollHeight, 120) + 'px'
                }}
              />
              <button
                id="send-chat"
                onClick={() => sendMessage()}
                disabled={loading || !input.trim()}
                style={{
                  width: 40, height: 40, borderRadius: 12, flexShrink: 0,
                  background: input.trim() ? 'linear-gradient(135deg, #7C3AED, #4F46E5)' : 'rgba(255,255,255,0.06)',
                  border: 'none', cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.2s',
                  boxShadow: input.trim() ? '0 0 20px rgba(124,58,237,0.3)' : 'none',
                }}>
                <Send size={16} color={input.trim() ? 'white' : 'rgba(255,255,255,0.3)'} />
              </button>
            </div>
            <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.2)', textAlign: 'center', marginTop: 8 }}>
              ASMIA has access to all your campaigns, analytics, and training data
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
