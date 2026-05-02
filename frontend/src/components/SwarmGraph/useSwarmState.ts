'use client'

/**
 * useSwarmState — Hook
 * Consumes the SSE stream for a goal and derives live agent state.
 * Maps raw backend log events → per-agent status + thought + iteration count.
 * All logic is in this hook; the graph component is purely presentational.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { resolveAgentId, AGENT_IDS } from './swarmConfig'
import { getToken } from '@/lib/auth'

export type AgentStatus = 'idle' | 'active' | 'complete' | 'error'

export interface AgentLiveState {
  status: AgentStatus
  lastThought: string
  lastAction: string
  iterationCount: number
  lastActiveAt: number | null
}

export type SwarmState = Record<string, AgentLiveState>

export interface SwarmEvent {
  agent: string
  thought: string
  action?: string
  level?: string
  timestamp?: string
}

/** How long (ms) an agent stays 'active' after its last event before going 'complete' */
const ACTIVE_DECAY_MS = 4_000

function buildInitialState(): SwarmState {
  return Object.fromEntries(
    AGENT_IDS.map(id => [
      id,
      { status: 'idle', lastThought: '', lastAction: '', iterationCount: 0, lastActiveAt: null },
    ])
  )
}

export function useSwarmState(goalId: string | null, goalStatus?: string) {
  const [state, setState] = useState<SwarmState>(buildInitialState)
  const [events, setEvents] = useState<SwarmEvent[]>([])
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const decayTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  /** Schedule decay of 'active' → 'complete' after ACTIVE_DECAY_MS */
  const scheduleDecay = useCallback((agentId: string) => {
    if (decayTimers.current[agentId]) clearTimeout(decayTimers.current[agentId])
    decayTimers.current[agentId] = setTimeout(() => {
      setState(prev => {
        if (prev[agentId]?.status !== 'active') return prev
        return {
          ...prev,
          [agentId]: { ...prev[agentId], status: 'complete' },
        }
      })
    }, ACTIVE_DECAY_MS)
  }, [])

  const processEvent = useCallback((raw: SwarmEvent) => {
    const agentId = resolveAgentId(raw.agent || 'orchestrator')
    const isError = raw.level === 'error'

    setState(prev => ({
      ...prev,
      [agentId]: {
        status: isError ? 'error' : 'active',
        lastThought: raw.thought || prev[agentId]?.lastThought || '',
        lastAction: raw.action || prev[agentId]?.lastAction || '',
        iterationCount: (prev[agentId]?.iterationCount ?? 0) + 1,
        lastActiveAt: Date.now(),
      },
    }))

    setEvents(prev => [
      { ...raw, agent: agentId },
      ...prev.slice(0, 199), // keep last 200 events
    ])

    if (!isError) scheduleDecay(agentId)
  }, [scheduleDecay])

  useEffect(() => {
    if (!goalId) return

    // Clean up any existing connection
    esRef.current?.close()
    setState(buildInitialState())
    setEvents([])

    const token = getToken()
    const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const url = `${BASE}/api/stream/goals/${goalId}${token ? `?token=${token}` : ''}`

    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => setConnected(true)

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        if (event.type === 'connected') {
          setConnected(true)
          return
        }
        if (event.type === 'ping' || event.type === 'stream_ended') return
        if (event.type === 'agent_log' || event.agent) {
          processEvent(event as SwarmEvent)
        }
      } catch {
        // silently ignore malformed events
      }
    }

    es.onerror = () => {
      setConnected(false)
      // EventSource auto-reconnects; no need to manually retry
    }

    return () => {
      es.close()
      esRef.current = null
      Object.values(decayTimers.current).forEach(clearTimeout)
      decayTimers.current = {}
    }
  }, [goalId, processEvent])

  // When goal reaches terminal state, mark all 'active' agents as 'complete'
  useEffect(() => {
    if (goalStatus === 'completed' || goalStatus === 'failed' || goalStatus === 'paused') {
      setState(prev => {
        const next = { ...prev }
        for (const id of AGENT_IDS) {
          if (next[id].status === 'active') {
            next[id] = { ...next[id], status: goalStatus === 'failed' ? 'error' : 'complete' }
          }
        }
        return next
      })
    }
  }, [goalStatus])

  return { state, events, connected }
}
