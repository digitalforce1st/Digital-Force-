/**
 * Digital Force — Swarm Graph Configuration
 * All agent topology, colors, and labels are defined here.
 * The graph renderer reads this config — nothing is hardcoded in rendering logic.
 */

export interface AgentConfig {
  id: string
  label: string
  shortLabel: string
  color: string
  glowColor: string
  description: string
  /** Fractional position in the graph canvas [0..1] */
  position: { x: number; y: number }
  /** Which agents this node sends data to */
  targets: string[]
  /** Role category for grouping */
  role: 'orchestrator' | 'research' | 'creative' | 'distribution' | 'oversight'
}

export const AGENT_CONFIGS: Record<string, AgentConfig> = {
  orchestrator: {
    id: 'orchestrator',
    label: 'God Node',
    shortLabel: 'GOD',
    color: '#F59E0B',
    glowColor: 'rgba(245,158,11,0.6)',
    description: 'LLM-driven supervisor. Makes all routing decisions from live state.',
    position: { x: 0.5, y: 0.15 },
    targets: ['researcher', 'strategist', 'monitor'],
    role: 'orchestrator',
  },
  researcher: {
    id: 'researcher',
    label: 'Researcher',
    shortLabel: 'RE',
    color: '#3B82F6',
    glowColor: 'rgba(59,130,246,0.6)',
    description: 'Scans live web trends, competitor intelligence, audience data.',
    position: { x: 0.15, y: 0.42 },
    targets: ['strategist'],
    role: 'research',
  },
  strategist: {
    id: 'strategist',
    label: 'Strategist',
    shortLabel: 'ST',
    color: '#8B5CF6',
    glowColor: 'rgba(139,92,246,0.6)',
    description: 'Builds the full campaign plan and generates the task list.',
    position: { x: 0.5, y: 0.42 },
    targets: ['content_director'],
    role: 'creative',
  },
  content_director: {
    id: 'content_director',
    label: 'Content Director',
    shortLabel: 'CD',
    color: '#EC4899',
    glowColor: 'rgba(236,72,153,0.6)',
    description: 'Writes all content across platforms in parallel.',
    position: { x: 0.82, y: 0.42 },
    targets: ['publisher'],
    role: 'creative',
  },
  publisher: {
    id: 'publisher',
    label: 'Publisher',
    shortLabel: 'PB',
    color: '#00A3FF',
    glowColor: 'rgba(0,163,255,0.6)',
    description: 'Distributes approved content to social platforms.',
    position: { x: 0.65, y: 0.72 },
    targets: ['skillforge'],
    role: 'distribution',
  },
  skillforge: {
    id: 'skillforge',
    label: 'SkillForge',
    shortLabel: 'SF',
    color: '#F97316',
    glowColor: 'rgba(249,115,22,0.6)',
    description: 'Auto-heals failures. Writes new skills when agents fail.',
    position: { x: 0.35, y: 0.72 },
    targets: ['orchestrator'],
    role: 'oversight',
  },
  monitor: {
    id: 'monitor',
    label: 'Monitor',
    shortLabel: 'MN',
    color: '#22D3EE',
    glowColor: 'rgba(34,211,238,0.6)',
    description: 'Compiles KPI snapshots and triggers replanning if needed.',
    position: { x: 0.15, y: 0.72 },
    targets: ['orchestrator'],
    role: 'oversight',
  },
  auditor: {
    id: 'auditor',
    label: 'Auditor',
    shortLabel: 'AU',
    color: '#10B981',
    glowColor: 'rgba(16,185,129,0.6)',
    description: 'Risk-scores actions and flags dangerous operations.',
    position: { x: 0.82, y: 0.72 },
    targets: ['orchestrator'],
    role: 'oversight',
  },
}

export const AGENT_IDS = Object.keys(AGENT_CONFIGS)

/**
 * Map raw agent name strings from the backend (which may use variations)
 * to canonical agent config IDs.
 */
export function resolveAgentId(raw: string): string {
  const lower = raw.toLowerCase().replace(/[-\s]/g, '_')
  if (AGENT_CONFIGS[lower]) return lower
  // Fuzzy match: find config whose id is contained in the raw string
  for (const id of AGENT_IDS) {
    if (lower.includes(id) || id.includes(lower)) return id
  }
  return 'orchestrator' // fallback
}
