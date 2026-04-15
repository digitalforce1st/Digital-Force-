'use client'

import { useState, useEffect } from 'react'
import Sidebar from '@/components/Sidebar'
import {
  Settings, Cpu, Share2, Bell, AlertTriangle, Eye, EyeOff,
  Save, CheckCircle2, AlertCircle, ChevronRight, RefreshCw, Trash2
} from 'lucide-react'
import api from '@/lib/api'

type Tab = 'general' | 'integrations' | 'notifications' | 'danger'

interface FieldProps {
  label: string; id: string; value: string; placeholder?: string
  isSecret?: boolean; onChange: (v: string) => void; hint?: string
  type?: string
}

function Field({ label, id, value, placeholder, isSecret, onChange, hint, type = 'text' }: FieldProps) {
  const [show, setShow] = useState(false)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label htmlFor={id} style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', fontWeight: 500 }}>
        {label}
      </label>
      <div style={{ position: 'relative' }}>
        <input
          id={id} type={isSecret && !show ? 'password' : type}
          value={value} onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          style={{
            width: '100%', padding: `0.6rem ${isSecret ? '2.75rem' : '0.875rem'} 0.6rem 0.875rem`,
            borderRadius: 10, background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.09)', color: '#fff',
            fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box',
            fontFamily: isSecret && !show ? 'monospace' : 'inherit',
          }}
        />
        {isSecret && (
          <button type="button" onClick={() => setShow(!show)}
            style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
              background: 'none', border: 'none', color: 'rgba(255,255,255,0.35)', cursor: 'pointer', padding: 4 }}>
            {show ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
      {hint && <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.25)' }}>{hint}</div>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1rem' }}>
      <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1.25rem', fontSize: '0.9rem' }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>{children}</div>
    </div>
  )
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('general')
  const [form, setForm] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [showDangerConfirm, setShowDangerConfirm] = useState(false)

  useEffect(() => {
    Promise.all([api.settings.get(), api.settings.status()])
      .then(([settings, st]) => {
        setForm(Object.fromEntries(
          Object.entries(settings).map(([k, v]) => [k, String(v ?? '')])
        ))
        setStatus(st)
      })
      .catch(e => setError(e.message))
  }, [])

  const set = (key: string) => (val: string) => setForm(f => ({ ...f, [key]: val }))

  const handleSave = async () => {
    setSaving(true); setError(''); setSaved(false)
    try {
      const payload: Record<string, unknown> = {}
      const saveable = ['groq_api_key','openai_api_key','buffer_access_token',
        'facebook_page_id','facebook_access_token','qdrant_url','qdrant_api_key',
        'smtp_host','smtp_port','smtp_username','smtp_password','smtp_from_name',
        'smtp_from_email','frontend_url','cors_origins','agent_max_iterations',
        'agent_timeout_seconds']
      for (const key of saveable) {
        if (form[key] !== undefined && !form[key].includes('•')) {
          payload[key] = form[key]
        }
      }
      await api.settings.update(payload)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      // Refresh status after save
      const st = await api.settings.status()
      setStatus(st)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleResetOverrides = async () => {
    await api.settings.resetOverrides()
    setShowDangerConfirm(false)
    window.location.reload()
  }

  const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: 'general', label: 'General', icon: Settings },
    { id: 'integrations', label: 'Integrations', icon: Cpu },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'danger', label: 'Danger Zone', icon: AlertTriangle },
  ]

  const llmStatus = status.llm as Record<string, boolean> | undefined
  const pubStatus = status.publishing as Record<string, boolean> | undefined

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto', maxWidth: 900, margin: '0 auto', width: '100%' }}>
        {/* Header */}
        <div className="animate-slide-up" style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: '#fff' }}>Settings</h1>
            <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.875rem', marginTop: 4 }}>
              Configure your Digital Force agency
            </p>
          </div>
          {activeTab !== 'danger' && (
            <button onClick={handleSave} disabled={saving} className="btn-primary" id="save-settings">
              {saving ? <RefreshCw size={15} className="animate-spin" /> :
               saved ? <CheckCircle2 size={15} /> : <Save size={15} />}
              {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Changes'}
            </button>
          )}
        </div>

        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: '1rem',
            padding: '0.75rem 1rem', borderRadius: 10,
            background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
            color: '#FCA5A5', fontSize: '0.85rem',
          }}>
            <AlertCircle size={15} /> {error}
          </div>
        )}

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: '1.5rem', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '0.75rem' }}>
          {TABS.map(tab => {
            const Icon = tab.icon
            return (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 7,
                  padding: '0.5rem 1rem', borderRadius: 10, fontSize: '0.85rem',
                  fontWeight: activeTab === tab.id ? 600 : 400, cursor: 'pointer',
                  background: activeTab === tab.id ? 'rgba(124,58,237,0.15)' : 'transparent',
                  color: activeTab === tab.id ? '#A78BFA' : 'rgba(255,255,255,0.45)',
                  border: `1px solid ${activeTab === tab.id ? 'rgba(124,58,237,0.25)' : 'transparent'}`,
                  transition: 'all 0.2s',
                }}>
                <Icon size={14} />
                {tab.id === 'danger'
                  ? <span style={{ color: activeTab === tab.id ? '#FCA5A5' : 'rgba(239,68,68,0.6)' }}>Danger Zone</span>
                  : tab.label}
              </button>
            )
          })}
        </div>

        {/* ── General ── */}
        {activeTab === 'general' && (
          <div>
            <Section title="Application">
              <Field id="frontend_url" label="Frontend URL" value={form.frontend_url || ''} onChange={set('frontend_url')} placeholder="http://localhost:3000" />
              <Field id="cors_origins" label="CORS Origins" value={form.cors_origins || ''} onChange={set('cors_origins')} placeholder="http://localhost:3000,https://yourdomain.com" hint="Comma-separated list of allowed origins" />
            </Section>
            <Section title="Agent Configuration">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <Field id="agent_max_iterations" label="Max Agent Iterations" type="number"
                  value={form.agent_max_iterations || '10'} onChange={set('agent_max_iterations')}
                  hint="How many steps an agent can take per task" />
                <Field id="agent_timeout_seconds" label="Agent Timeout (seconds)" type="number"
                  value={form.agent_timeout_seconds || '300'} onChange={set('agent_timeout_seconds')}
                  hint="Max time for a single agent run" />
              </div>
            </Section>
          </div>
        )}

        {/* ── Integrations ── */}
        {activeTab === 'integrations' && (
          <div>
            {/* LLM Status Banner */}
            <div style={{ display: 'flex', gap: 8, marginBottom: '1.25rem' }}>
              {[
                { label: 'Groq', ok: llmStatus?.groq },
                { label: 'OpenAI', ok: llmStatus?.openai },
                { label: 'Buffer', ok: pubStatus?.buffer },
                { label: 'Facebook', ok: pubStatus?.facebook },
              ].map(({ label, ok }) => (
                <div key={label} style={{
                  display: 'flex', alignItems: 'center', gap: 6, padding: '0.35rem 0.75rem',
                  borderRadius: 8, fontSize: '0.78rem', fontWeight: 500,
                  background: ok ? 'rgba(52,211,153,0.1)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${ok ? 'rgba(52,211,153,0.25)' : 'rgba(255,255,255,0.08)'}`,
                  color: ok ? '#34D399' : 'rgba(255,255,255,0.35)',
                }}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: ok ? '#34D399' : 'rgba(255,255,255,0.2)' }} />
                  {label}
                </div>
              ))}
            </div>

            <Section title="🤖 AI Language Models">
              <Field id="groq_api_key" label="Groq API Key (Primary — fastest)" value={form.groq_api_key || ''} onChange={set('groq_api_key')} isSecret placeholder="gsk_..." hint="Get yours at console.groq.com — llama-3.3-70b-versatile" />
              <Field id="openai_api_key" label="OpenAI API Key (Reasoning fallback)" value={form.openai_api_key || ''} onChange={set('openai_api_key')} isSecret placeholder="sk-..." hint="Used for GPT-4o reasoning tasks and image generation" />
            </Section>

            <Section title="📱 Social Publishing">
              <Field id="buffer_access_token" label="Buffer Access Token" value={form.buffer_access_token || ''} onChange={set('buffer_access_token')} isSecret placeholder="buffer_pub_..." hint="Get from buffer.com/developers" />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <Field id="facebook_page_id" label="Facebook Page ID" value={form.facebook_page_id || ''} onChange={set('facebook_page_id')} placeholder="123456789" />
                <Field id="facebook_access_token" label="Facebook Access Token" value={form.facebook_access_token || ''} onChange={set('facebook_access_token')} isSecret placeholder="EAA..." />
              </div>
            </Section>

            <Section title="🧠 Vector Database (Qdrant)">
              <Field id="qdrant_url" label="Qdrant Cloud URL" value={form.qdrant_url || ''} onChange={set('qdrant_url')} placeholder="https://xxx.qdrant.io" hint="Leave empty to use local Qdrant storage" />
              <Field id="qdrant_api_key" label="Qdrant API Key" value={form.qdrant_api_key || ''} onChange={set('qdrant_api_key')} isSecret placeholder="your-qdrant-api-key" />
            </Section>
          </div>
        )}

        {/* ── Notifications ── */}
        {activeTab === 'notifications' && (
          <div>
            <Section title="📧 SMTP Email (for approval notifications)">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <Field id="smtp_host" label="SMTP Host" value={form.smtp_host || ''} onChange={set('smtp_host')} placeholder="smtp.gmail.com" />
                <Field id="smtp_port" label="SMTP Port" type="number" value={form.smtp_port || '587'} onChange={set('smtp_port')} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <Field id="smtp_username" label="Email Address" value={form.smtp_username || ''} onChange={set('smtp_username')} placeholder="you@gmail.com" />
                <Field id="smtp_password" label="App Password" value={form.smtp_password || ''} onChange={set('smtp_password')} isSecret placeholder="••••••••••••" />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <Field id="smtp_from_name" label="From Name" value={form.smtp_from_name || ''} onChange={set('smtp_from_name')} placeholder="Digital Force" />
                <Field id="smtp_from_email" label="From Email" value={form.smtp_from_email || ''} onChange={set('smtp_from_email')} placeholder="noreply@yourdomain.com" />
              </div>
              <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.3)', padding: '0.75rem', background: 'rgba(255,255,255,0.03)', borderRadius: 8 }}>
                💡 For Gmail: Enable 2FA → Generate an App Password at myaccount.google.com/apppasswords
              </div>
            </Section>
          </div>
        )}

        {/* ── Danger Zone ── */}
        {activeTab === 'danger' && (
          <div className="glass-panel" style={{ padding: '1.5rem', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 16 }}>
            <div style={{ fontWeight: 600, color: '#FCA5A5', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertTriangle size={18} /> Danger Zone
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '1rem', borderRadius: 12, background: 'rgba(239,68,68,0.05)' }}>
                <div>
                  <div style={{ color: '#fff', fontWeight: 500, fontSize: '0.9rem' }}>Reset Setting Overrides</div>
                  <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem', marginTop: 2 }}>
                    Revert to .env defaults. API keys entered in UI will be cleared.
                  </div>
                </div>
                {!showDangerConfirm ? (
                  <button onClick={() => setShowDangerConfirm(true)} className="btn-danger" style={{ flexShrink: 0 }}>
                    <Trash2 size={14} /> Reset
                  </button>
                ) : (
                  <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                    <button onClick={() => setShowDangerConfirm(false)} className="btn-ghost" style={{ fontSize: '0.8rem' }}>Cancel</button>
                    <button onClick={handleResetOverrides} className="btn-danger" style={{ fontSize: '0.8rem' }}>
                      Yes, reset
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
