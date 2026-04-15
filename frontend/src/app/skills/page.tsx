'use client'

import { useState, useEffect } from 'react'
import Sidebar from '@/components/Sidebar'
import { Cpu, Code, ToggleLeft, ToggleRight, Trash2, Zap, ChevronDown, ChevronUp } from 'lucide-react'
import api from '@/lib/api'

interface Skill {
  id: string
  name: string
  display_name: string
  description: string
  code?: string
  test_passed: boolean
  usage_count: number
  is_active: boolean
  sandbox_test_result?: string
  created_at: string
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    api.skills.list().then(setSkills).finally(() => setLoading(false))
  }, [])

  const toggleSkill = async (id: string) => {
    const res = await api.skills.toggle(id)
    setSkills(prev => prev.map(s => s.id === id ? { ...s, is_active: res.is_active } : s))
  }

  const deleteSkill = async (id: string) => {
    await api.skills.delete(id)
    setSkills(prev => prev.filter(s => s.id !== id))
  }

  const loadCode = async (id: string) => {
    if (expanded === id) { setExpanded(null); return }
    const skill = await api.skills.get(id)
    setSkills(prev => prev.map(s => s.id === id ? { ...s, code: skill.code, sandbox_test_result: skill.sandbox_test_result } : s))
    setExpanded(id)
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">

        <div className="mb-8 animate-slide-up flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-2xl flex items-center justify-center"
                   style={{ background: 'linear-gradient(135deg, #EF4444 0%, #7C3AED 100%)' }}>
                <Cpu size={20} className="text-white" />
              </div>
              <h1 className="text-2xl font-bold text-white">SkillForge</h1>
            </div>
            <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.875rem' }}>
              Python skills autonomously created by the agent to handle novel tasks.
              Every skill is sandbox-tested before registration.
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: 'Total Skills', value: skills.length, color: '#A78BFA' },
            { label: 'Active Skills', value: skills.filter(s => s.is_active).length, color: '#34D399' },
            { label: 'Total Uses', value: skills.reduce((a, s) => a + s.usage_count, 0), color: '#22D3EE' },
          ].map((s, i) => (
            <div key={i} className="glass-panel p-5 flex items-center gap-4">
              <div className="text-3xl font-bold" style={{ color: s.color }}>{s.value}</div>
              <div className="text-sm" style={{ color: 'rgba(255,255,255,0.45)' }}>{s.label}</div>
            </div>
          ))}
        </div>

        {loading ? (
          <div className="flex justify-center py-16">
            <div className="flex gap-1"><div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" /></div>
          </div>
        ) : skills.length === 0 ? (
          <div className="glass-panel p-16 flex flex-col items-center text-center">
            <div className="w-16 h-16 rounded-3xl flex items-center justify-center mb-4"
                 style={{ background: 'rgba(239,68,68,0.1)' }}>
              <Zap size={28} style={{ color: '#EF4444' }} />
            </div>
            <h3 className="font-bold text-white mb-2">No skills forged yet</h3>
            <p className="text-sm" style={{ color: 'rgba(255,255,255,0.4)' }}>
              When the agent encounters a task it can't handle, it will automatically create a new skill here.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {skills.map(skill => (
              <div key={skill.id} className="glass-panel overflow-hidden animate-slide-up">
                <div className="p-5 flex items-start gap-4">
                  <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
                       style={{ background: skill.test_passed ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)' }}>
                    <Code size={18} style={{ color: skill.test_passed ? '#34D399' : '#EF4444' }} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm text-white">{skill.display_name}</span>
                      <span className="text-xs px-2 py-0.5 rounded-md font-mono"
                            style={{ background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)' }}>
                        {skill.name}
                      </span>
                      {skill.test_passed
                        ? <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(16,185,129,0.1)', color: '#34D399' }}>✓ Tested</span>
                        : <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(239,68,68,0.1)', color: '#F87171' }}>✗ Untested</span>}
                    </div>
                    <p className="text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>{skill.description}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
                      <span>Used {skill.usage_count} times</span>
                      <span>·</span>
                      <span>{new Date(skill.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button onClick={() => loadCode(skill.id)} className="btn-ghost text-xs p-2">
                      {expanded === skill.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                    <button onClick={() => toggleSkill(skill.id)} className="btn-ghost text-xs p-2">
                      {skill.is_active
                        ? <ToggleRight size={20} className="text-green-400" />
                        : <ToggleLeft size={20} style={{ color: 'rgba(255,255,255,0.3)' }} />}
                    </button>
                    <button onClick={() => deleteSkill(skill.id)} className="btn-ghost text-xs p-2 text-red-400/50 hover:text-red-400">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {/* Code viewer */}
                {expanded === skill.id && skill.code && (
                  <div className="border-t" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                    <pre className="p-5 text-xs overflow-x-auto font-mono leading-relaxed"
                         style={{ color: '#A78BFA', background: 'rgba(0,0,0,0.2)', maxHeight: '300px' }}>
                      {skill.code}
                    </pre>
                    {skill.sandbox_test_result && (
                      <div className="px-5 py-3 text-xs font-mono border-t" style={{ borderColor: 'rgba(255,255,255,0.04)', color: '#34D399', background: 'rgba(16,185,129,0.04)' }}>
                        <div className="text-white/30 mb-1">Test Output:</div>
                        {skill.sandbox_test_result}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
