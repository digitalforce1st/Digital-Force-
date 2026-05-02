'use client'

/**
 * SwarmGraph — Main component
 * Renders the live agent network using React Flow (@xyflow/react).
 *
 * Architecture:
 *   - useSwarmState() owns all SSE + state logic
 *   - AgentNode renders each agent node
 *   - AnimatedEdge renders live data-flow edges
 *   - No hardcoded positions/colors — all from swarmConfig.ts
 */

import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
  type NodeTypes,
  type EdgeTypes,
  ReactFlowProvider,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { motion, AnimatePresence } from 'framer-motion'

import { AGENT_CONFIGS, AGENT_IDS, type AgentConfig } from './swarmConfig'
import AgentNode, { type AgentNodeData } from './AgentNode'
import AnimatedEdge, { type AnimatedEdgeData } from './AnimatedEdge'
import { useSwarmState } from './useSwarmState'
import type { SwarmEvent } from './useSwarmState'

// Register custom node and edge types
const nodeTypes: NodeTypes = { agentNode: AgentNode }
const edgeTypes: EdgeTypes = { animatedEdge: AnimatedEdge }

// ── Build static graph topology from config ──────────────────────────────────

function buildTopology(containerWidth: number, containerHeight: number) {
  const nodes: Node[] = []
  const edges: Edge[] = []

  for (const cfg of Object.values(AGENT_CONFIGS)) {
    nodes.push({
      id: cfg.id,
      type: 'agentNode',
      position: {
        x: cfg.position.x * containerWidth - 48, // center the 96px node
        y: cfg.position.y * containerHeight,
      },
      data: {
        config: cfg,
        status: 'idle',
        lastThought: '',
        iterationCount: 0,
      } satisfies AgentNodeData,
      draggable: true,
    })

    for (const targetId of cfg.targets) {
      edges.push({
        id: `${cfg.id}->${targetId}`,
        source: cfg.id,
        target: targetId,
        type: 'animatedEdge',
        data: {
          active: false,
          color: cfg.color,
        } satisfies AnimatedEdgeData,
        animated: false,
      })
    }
  }

  return { nodes, edges }
}

// ── Inner graph component (needs ReactFlowProvider above it) ─────────────────

interface SwarmGraphInnerProps {
  goalId: string | null
  goalStatus?: string
  width: number
  height: number
}

function SwarmGraphInner({ goalId, goalStatus, width, height }: SwarmGraphInnerProps) {
  const { state: swarmState, events, connected } = useSwarmState(goalId, goalStatus)

  const { nodes: initNodes, edges: initEdges } = useMemo(
    () => buildTopology(width, height),
    [width, height]
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initEdges)

  // Sync live agent state → node data
  useMemo(() => {
    setNodes(nds =>
      nds.map(node => {
        const live = swarmState[node.id]
        if (!live) return node
        return {
          ...node,
          data: {
            ...(node.data as AgentNodeData),
            status: live.status,
            lastThought: live.lastThought,
            iterationCount: live.iterationCount,
          },
        }
      })
    )

    // Activate edges from active agents
    setEdges(eds =>
      eds.map(edge => {
        const srcLive = swarmState[edge.source]
        const isActive = srcLive?.status === 'active'
        const cfg = AGENT_CONFIGS[edge.source]
        return {
          ...edge,
          data: {
            active: isActive,
            color: cfg?.color ?? '#334155',
          } satisfies AnimatedEdgeData,
        }
      })
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [swarmState])

  const activeCount = AGENT_IDS.filter(id => swarmState[id]?.status === 'active').length
  const completeCount = AGENT_IDS.filter(id => swarmState[id]?.status === 'complete').length
  const latestEvent: SwarmEvent | undefined = events[0]

  return (
    <div style={{ position: 'relative', width, height }}>
      {/* SVG defs for arrowhead markers */}
      <svg style={{ position: 'absolute', width: 0, height: 0 }}>
        <defs>
          {Object.values(AGENT_CONFIGS).map(cfg => (
            <marker
              key={cfg.color}
              id={`arrowhead-${cfg.color.replace('#', '')}`}
              markerWidth="8" markerHeight="8"
              refX="6" refY="3"
              orient="auto"
            >
              <path d="M0,0 L0,6 L8,3 z" fill={cfg.color} />
            </marker>
          ))}
        </defs>
      </svg>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.4}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        style={{ background: 'transparent' }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1}
          color="rgba(255,255,255,0.04)"
        />
        <Controls
          style={{
            background: 'rgba(15,23,42,0.8)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 10,
          }}
        />
        <MiniMap
          nodeColor={(node) => {
            const nd = node.data as AgentNodeData
            if (nd?.status === 'active') return nd.config?.color ?? '#334155'
            if (nd?.status === 'complete') return `${nd.config?.color ?? '#334155'}60`
            return 'rgba(255,255,255,0.06)'
          }}
          maskColor="rgba(8,11,18,0.7)"
          style={{
            background: 'rgba(15,23,42,0.8)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 10,
          }}
        />
      </ReactFlow>

      {/* Status overlay — top-right corner */}
      <div style={{
        position: 'absolute', top: 12, right: 12,
        display: 'flex', flexDirection: 'column', gap: 6,
        zIndex: 10, pointerEvents: 'none',
      }}>
        {/* Connection status */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '0.3rem 0.75rem', borderRadius: 8,
          background: 'rgba(8,11,18,0.9)', border: '1px solid rgba(255,255,255,0.06)',
          backdropFilter: 'blur(12px)',
        }}>
          <motion.span
            animate={{ opacity: connected ? [1, 0.4, 1] : 0.3 }}
            transition={{ repeat: Infinity, duration: 1.5 }}
            style={{ width: 6, height: 6, borderRadius: '50%', background: connected ? '#10B981' : '#475569', display: 'block' }}
          />
          <span style={{ fontSize: '0.65rem', fontWeight: 700, color: connected ? '#10B981' : '#475569', letterSpacing: '0.06em' }}>
            {connected ? 'LIVE' : 'DISCONNECTED'}
          </span>
        </div>

        {/* Agent activity counters */}
        {(activeCount > 0 || completeCount > 0) && (
          <div style={{
            padding: '0.4rem 0.75rem', borderRadius: 8,
            background: 'rgba(8,11,18,0.9)', border: '1px solid rgba(255,255,255,0.06)',
            backdropFilter: 'blur(12px)',
            display: 'flex', gap: 10,
          }}>
            {activeCount > 0 && (
              <span style={{ fontSize: '0.65rem', fontWeight: 700, color: '#F59E0B', letterSpacing: '0.05em' }}>
                {activeCount} ACTIVE
              </span>
            )}
            {completeCount > 0 && (
              <span style={{ fontSize: '0.65rem', fontWeight: 700, color: '#10B981', letterSpacing: '0.05em' }}>
                {completeCount} DONE
              </span>
            )}
          </div>
        )}
      </div>

      {/* Live thought ticker — bottom */}
      <AnimatePresence mode="popLayout">
        {latestEvent && (
          <motion.div
            key={latestEvent.thought?.slice(0, 20)}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}
            style={{
              position: 'absolute', bottom: 12, left: 12, right: 60,
              padding: '0.5rem 0.875rem', borderRadius: 10,
              background: 'rgba(8,11,18,0.9)', border: `1px solid ${AGENT_CONFIGS[latestEvent.agent]?.color ?? '#334155'}30`,
              backdropFilter: 'blur(12px)',
              display: 'flex', alignItems: 'flex-start', gap: 8,
              zIndex: 10, pointerEvents: 'none',
            }}
          >
            <span style={{
              fontSize: '0.6rem', fontWeight: 900, letterSpacing: '0.06em',
              color: AGENT_CONFIGS[latestEvent.agent]?.color ?? '#94A3B8',
              flexShrink: 0, paddingTop: 1,
            }}>
              {(AGENT_CONFIGS[latestEvent.agent]?.label ?? latestEvent.agent).toUpperCase()}
            </span>
            <span style={{ fontSize: '0.7rem', color: '#64748B', lineHeight: 1.5, overflow: 'hidden' }}>
              {latestEvent.thought?.slice(0, 140)}{(latestEvent.thought?.length ?? 0) > 140 ? '…' : ''}
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Public export — wrapped in ReactFlowProvider ─────────────────────────────

interface SwarmGraphProps {
  goalId: string | null
  goalStatus?: string
  width?: number
  height?: number
  className?: string
  style?: React.CSSProperties
}

export default function SwarmGraph({
  goalId,
  goalStatus,
  width = 800,
  height = 500,
  className,
  style,
}: SwarmGraphProps) {
  return (
    <div
      className={className}
      style={{
        width, height,
        borderRadius: 16,
        overflow: 'hidden',
        background: 'linear-gradient(135deg, rgba(8,11,18,0.95) 0%, rgba(15,23,42,0.8) 100%)',
        border: '1px solid rgba(255,255,255,0.05)',
        position: 'relative',
        ...style,
      }}
    >
      <ReactFlowProvider>
        <SwarmGraphInner
          goalId={goalId}
          goalStatus={goalStatus}
          width={width}
          height={height}
        />
      </ReactFlowProvider>
    </div>
  )
}
