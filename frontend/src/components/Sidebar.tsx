'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import {
  Zap, LayoutDashboard, Target, BarChart2,
  BookOpen, Image, Cpu, Settings, MessageSquare,
  LogOut, AlertCircle, Activity,
} from 'lucide-react'
import { clearToken, getUser } from '@/lib/auth'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface NavItem {
  href: string
  label: string
  icon: React.ElementType
  badge?: number | string
  accent?: string
}

export default function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const user = getUser()
  const [awaitingCount, setAwaitingCount] = useState(0)
  const [agentStatus, setAgentStatus] = useState<'idle' | 'planning' | 'executing' | 'awaiting'>('idle')

  useEffect(() => {
    // Poll for goal statuses every 15 seconds
    const check = async () => {
      try {
        const goals = await api.goals.list()
        const awaiting = goals.filter(g => g.status === 'awaiting_approval').length
        const executing = goals.filter(g => g.status === 'executing').length
        const planning = goals.filter(g => g.status === 'planning').length

        setAwaitingCount(awaiting)
        if (executing > 0) setAgentStatus('executing')
        else if (planning > 0) setAgentStatus('planning')
        else if (awaiting > 0) setAgentStatus('awaiting')
        else setAgentStatus('idle')
      } catch { /* no-op */ }
    }
    check()
    const interval = setInterval(check, 15000)
    return () => clearInterval(interval)
  }, [])

  const NAV: NavItem[] = [
    { href: '/chat', label: 'Talk to Agency', icon: MessageSquare, accent: '#A78BFA' },
    { href: '/', label: 'Mission Control', icon: LayoutDashboard },
    { href: '/goals', label: 'Missions', icon: Target, badge: awaitingCount || undefined },
    { href: '/analytics', label: 'Analytics', icon: BarChart2 },
    { href: '/training', label: 'Knowledge Base', icon: BookOpen },
    { href: '/media', label: 'Media Library', icon: Image },
    { href: '/skills', label: 'SkillForge', icon: Cpu },
    { href: '/settings', label: 'Settings', icon: Settings },
  ]

  const STATUS_CONFIG = {
    idle:      { label: 'Idle', color: '#4B5563', dot: '#6B7280' },
    planning:  { label: 'Planning...', color: '#A78BFA', dot: '#7C3AED' },
    executing: { label: 'Executing', color: '#34D399', dot: '#10B981' },
    awaiting:  { label: 'Needs Approval', color: '#FCD34D', dot: '#F59E0B' },
  }
  const st = STATUS_CONFIG[agentStatus]

  const handleLogout = () => {
    clearToken()
    router.push('/login')
  }

  return (
    <aside style={{
      width: 220, minHeight: '100vh', flexShrink: 0,
      background: 'rgba(255,255,255,0.025)',
      borderRight: '1px solid rgba(255,255,255,0.06)',
      display: 'flex', flexDirection: 'column',
      position: 'sticky', top: 0, height: '100vh',
    }}>
      {/* Logo */}
      <div style={{ padding: '1.25rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <Link href="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
          <div style={{
            width: 34, height: 34, borderRadius: 10,
            background: 'linear-gradient(135deg, #7C3AED, #4F46E5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 20px rgba(124,58,237,0.35)',
          }}>
            <Zap size={17} color="white" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff', lineHeight: 1.1 }}>Digital Force</div>
            <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.35)' }}>ASMIA Platform</div>
          </div>
        </Link>
      </div>

      {/* Agent status badge */}
      <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '0.45rem 0.75rem',
          borderRadius: 10, background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.06)',
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: st.dot,
            boxShadow: agentStatus !== 'idle' ? `0 0 8px ${st.dot}` : 'none',
            animation: agentStatus === 'executing' ? 'pulse 2s infinite' : 'none',
          }} />
          <div>
            <div style={{ fontSize: '0.7rem', color: st.color, fontWeight: 500 }}>{st.label}</div>
            <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.25)' }}>Agent status</div>
          </div>
          {agentStatus === 'executing' && <Activity size={12} style={{ color: '#34D399', marginLeft: 'auto' }} />}
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '0.75rem 0.75rem', overflowY: 'auto' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {NAV.map(item => {
            const Icon = item.icon
            const active = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href))
            const isChatLink = item.href === '/chat'

            return (
              <Link key={item.href} href={item.href}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: isChatLink ? '0.6rem 0.75rem' : '0.5rem 0.75rem',
                  borderRadius: 10, textDecoration: 'none', transition: 'all 0.15s',
                  background: active
                    ? isChatLink ? 'rgba(124,58,237,0.2)' : 'rgba(255,255,255,0.07)'
                    : 'transparent',
                  color: active
                    ? isChatLink ? '#A78BFA' : '#fff'
                    : 'rgba(255,255,255,0.45)',
                  border: active
                    ? `1px solid ${isChatLink ? 'rgba(124,58,237,0.3)' : 'rgba(255,255,255,0.08)'}`
                    : '1px solid transparent',
                  position: 'relative',
                  marginBottom: isChatLink ? 4 : 0,
                }}>
                <Icon size={16} style={{ flexShrink: 0, color: active && isChatLink ? '#A78BFA' : 'inherit' }} />
                <span style={{ fontSize: '0.85rem', fontWeight: active ? 600 : 400, flex: 1 }}>
                  {item.label}
                </span>
                {item.badge ? (
                  <span style={{
                    minWidth: 18, height: 18, borderRadius: 9, padding: '0 5px',
                    background: '#F59E0B', color: '#000', fontSize: '0.65rem',
                    fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {item.badge}
                  </span>
                ) : null}
              </Link>
            )
          })}
        </div>
      </nav>

      {/* User + Logout */}
      <div style={{ padding: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
        {user && (
          <div style={{ padding: '0.6rem 0.75rem', marginBottom: 6,
            borderRadius: 10, background: 'rgba(255,255,255,0.03)' }}>
            <div style={{ fontSize: '0.8rem', color: '#fff', fontWeight: 500 }}>
              {user.full_name || user.email?.split('@')[0] || 'User'}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.3)', marginTop: 2 }}>
              {user.role || 'operator'}
            </div>
          </div>
        )}
        <button onClick={handleLogout}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', gap: 8,
            padding: '0.5rem 0.75rem', borderRadius: 10, cursor: 'pointer',
            background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)',
            fontSize: '0.82rem', transition: 'all 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.08)'; e.currentTarget.style.color = '#FCA5A5' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'rgba(255,255,255,0.3)' }}>
          <LogOut size={14} /> Sign out
        </button>
      </div>
    </aside>
  )
}
