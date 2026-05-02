'use client'

/**
 * AnimatedEdge — Custom React Flow Edge
 * Draws a flowing animated line between agent nodes when data is in transit.
 * Uses SVG path animation driven by the 'active' prop.
 */

import { memo } from 'react'
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react'

export interface AnimatedEdgeData extends Record<string, unknown> {
  active: boolean
  color: string
}

function AnimatedEdge({
  id,
  sourceX, sourceY, targetX, targetY,
  sourcePosition, targetPosition,
  data,
}: EdgeProps) {
  const edgeData = data as AnimatedEdgeData
  const active = edgeData?.active ?? false
  const color = edgeData?.color ?? '#334155'

  const [edgePath] = getSmoothStepPath({
    sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition,
    borderRadius: 12,
  })

  return (
    <>
      {/* Base edge stroke */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: active ? color : 'rgba(255,255,255,0.05)',
          strokeWidth: active ? 2 : 1,
          transition: 'stroke 0.4s ease, stroke-width 0.4s ease',
        }}
        markerEnd={active ? `url(#arrowhead-${color.replace('#', '')})` : undefined}
      />

      {/* Animated pulse dot that travels along the edge when active */}
      {active && (
        <circle r={4} fill={color} style={{ filter: `drop-shadow(0 0 6px ${color})` }}>
          <animateMotion
            dur="1.2s"
            repeatCount="indefinite"
            path={edgePath}
            calcMode="linear"
          />
        </circle>
      )}
    </>
  )
}

export default memo(AnimatedEdge)
