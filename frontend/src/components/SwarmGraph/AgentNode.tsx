'use client'

/**
 * AgentNode — Custom React Flow Node
 * Renders a single agent in the swarm graph with live state animation.
 */

import { memo, useEffect, useState } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { motion, AnimatePresence } from 'framer-motion'
import type { AgentConfig } from './swarmConfig'

export interface AgentNodeData extends Record<string, unknown> {
  config: AgentConfig
  status: 'idle' | 'active' | 'complete' | 'error'
  lastThought: string
  iterationCount: number
}

function AgentNode({ data }: NodeProps) {
  const nodeData = data as AgentNodeData
  const { config, status, lastThought, iterationCount } = nodeData
  const [showTooltip, setShowTooltip] = useState(false)
  const [prevStatus, setPrevStatus] = useState(status)
  const [flashActive, setFlashActive] = useState(false)

  // Flash effect when status becomes active
  useEffect(() => {
    if (status === 'active' && prevStatus !== 'active') {
      setFlashActive(true)
      const t = setTimeout(() => setFlashActive(false), 800)
      return () => clearTimeout(t)
    }
    setPrevStatus(status)
  }, [status, prevStatus])

  const isActive = status === 'active'
  const isComplete = status === 'complete'
  const isError = status === 'error'

  const borderColor = isError
    ? 'rgba(239,68,68,0.8)'
    : isActive
    ? config.color
    : isComplete
    ? `${config.color}60`
    : 'rgba(255,255,255,0.08)'

  const bgColor = isActive
    ? `${config.color}18`
    : isComplete
    ? `${config.color}0D`
    : 'rgba(15,23,42,0.7)'

  const glowStyle = isActive
    ? { boxShadow: `0 0 24px ${config.glowColor}, 0 0 48px ${config.glowColor}60` }
    : isComplete
    ? { boxShadow: `0 0 12px ${config.glowColor}40` }
    : {}

  return (
    <div
      style={{ position: 'relative' }}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      {/* Handles — invisible, used by React Flow for edge connections */}
      <Handle type="target" position={Position.Top} style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Left} style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />

      {/* Flash ring on activation */}
      <AnimatePresence>
        {flashActive && (
          <motion.div
            initial={{ opacity: 0.8, scale: 1 }}
            animate={{ opacity: 0, scale: 1.8 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            style={{
              position: 'absolute', inset: -4,
              borderRadius: 14,
              border: `2px solid ${config.color}`,
              pointerEvents: 'none',
              zIndex: 0,
            }}
          />
        )}
      </AnimatePresence>

      {/* Main node body */}
      <motion.div
        animate={{
          borderColor,
          backgroundColor: bgColor,
          ...glowStyle,
        }}
        transition={{ duration: 0.35 }}
        style={{
          width: 96,
          height: 96,
          borderRadius: 16,
          border: `1.5px solid ${borderColor}`,
          background: bgColor,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          cursor: 'pointer',
          position: 'relative',
          zIndex: 1,
          backdropFilter: 'blur(12px)',
          ...glowStyle,
        }}
      >
        {/* Icon badge */}
        <motion.div
          animate={{ scale: isActive ? [1, 1.12, 1] : 1 }}
          transition={{ repeat: isActive ? Infinity : 0, duration: 1.4, ease: 'easeInOut' }}
          style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            background: isActive ? `${config.color}25` : `${config.color}12`,
            border: `1px solid ${config.color}${isActive ? '50' : '25'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span style={{
            fontSize: '0.65rem',
            fontWeight: 900,
            color: config.color,
            letterSpacing: '0.04em',
            fontFamily: 'JetBrains Mono, monospace',
          }}>
            {config.shortLabel}
          </span>
        </motion.div>

        {/* Label */}
        <span style={{
          fontSize: '0.58rem',
          fontWeight: 700,
          color: isActive ? '#F8FAFC' : '#64748B',
          letterSpacing: '0.05em',
          textAlign: 'center',
          lineHeight: 1.2,
          maxWidth: 80,
        }}>
          {config.label.toUpperCase()}
        </span>

        {/* Active indicator dots */}
        {isActive && (
          <div style={{ display: 'flex', gap: 3, position: 'absolute', bottom: 8 }}>
            {[0, 1, 2].map(i => (
              <motion.span
                key={i}
                animate={{ opacity: [0.3, 1, 0.3], scale: [1, 1.3, 1] }}
                transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.2 }}
                style={{ width: 3, height: 3, borderRadius: '50%', background: config.color, display: 'block' }}
              />
            ))}
          </div>
        )}

        {/* Complete checkmark */}
        {isComplete && !isActive && (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            style={{
              position: 'absolute',
              top: -6, right: -6,
              width: 16, height: 16,
              borderRadius: '50%',
              background: config.color,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.55rem',
              color: '#000',
              fontWeight: 900,
            }}
          >
            ✓
          </motion.div>
        )}

        {/* Error indicator */}
        {isError && (
          <motion.div
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ repeat: Infinity, duration: 1 }}
            style={{
              position: 'absolute',
              top: -6, right: -6,
              width: 16, height: 16,
              borderRadius: '50%',
              background: '#EF4444',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.6rem',
              color: '#fff',
              fontWeight: 900,
            }}
          >
            !
          </motion.div>
        )}

        {/* Iteration badge */}
        {iterationCount > 0 && (
          <div style={{
            position: 'absolute',
            top: -6, left: -6,
            minWidth: 16, height: 16,
            borderRadius: 8,
            background: 'rgba(15,23,42,0.95)',
            border: `1px solid ${config.color}40`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '0 4px',
          }}>
            <span style={{ fontSize: '0.5rem', fontWeight: 900, color: config.color }}>
              ×{iterationCount}
            </span>
          </div>
        )}
      </motion.div>

      {/* Tooltip */}
      <AnimatePresence>
        {showTooltip && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            style={{
              position: 'absolute',
              bottom: '100%',
              left: '50%',
              transform: 'translateX(-50%)',
              marginBottom: 10,
              width: 200,
              padding: '0.75rem',
              borderRadius: 10,
              background: 'rgba(8,11,18,0.97)',
              border: `1px solid ${config.color}35`,
              boxShadow: `0 8px 32px rgba(0,0,0,0.6), 0 0 20px ${config.glowColor}30`,
              pointerEvents: 'none',
              zIndex: 100,
            }}
          >
            <div style={{ fontSize: '0.72rem', fontWeight: 800, color: config.color, marginBottom: 4, letterSpacing: '0.03em' }}>
              {config.label}
            </div>
            <div style={{ fontSize: '0.68rem', color: '#64748B', lineHeight: 1.5, marginBottom: lastThought ? 8 : 0 }}>
              {config.description}
            </div>
            {lastThought && (
              <div style={{
                marginTop: 6,
                padding: '0.5rem',
                borderRadius: 6,
                background: `${config.color}10`,
                border: `1px solid ${config.color}20`,
              }}>
                <div style={{ fontSize: '0.6rem', fontWeight: 700, color: config.color, marginBottom: 3, letterSpacing: '0.06em' }}>
                  LAST THOUGHT
                </div>
                <div style={{ fontSize: '0.65rem', color: '#94A3B8', lineHeight: 1.5 }}>
                  {lastThought.slice(0, 120)}{lastThought.length > 120 ? '…' : ''}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default memo(AgentNode)
