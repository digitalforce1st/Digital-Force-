'use client'

import { useState, useEffect } from 'react'
import Sidebar from '@/components/Sidebar'
import {
  TrendingUp, Target, CheckCircle2, AlertCircle, Activity,
  Clock, Zap, BarChart2, Globe, BookOpen, Image, Star
} from 'lucide-react'
import api, { AnalyticsOverview } from '@/lib/api'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  BarChart, Bar, PieChart, Pie, Cell, CartesianGrid
} from 'recharts'

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: '#0A66C2', facebook: '#1877F2', twitter: '#1DA1F2',
  tiktok: '#FF0050', instagram: '#E1306C', youtube: '#FF0000', unknown: '#6B7280',
}

const PLATFORM_EMOJI: Record<string, string> = {
  linkedin: '💼', facebook: '👥', twitter: '🐦',
  tiktok: '🎵', instagram: '📸', youtube: '▶️',
}

const STATUS_COLORS: Record<string, string> = {
  planning: '#A78BFA', awaiting_approval: '#FCD34D',
  executing: '#34D399', monitoring: '#22D3EE',
  complete: '#6EE7B7', failed: '#FCA5A5',
}

function StatCard({ label, value, icon: Icon, color, sublabel }: {
  label: string; value: string | number; icon: React.ElementType;
  color: string; sublabel?: string
}) {
  return (
    <div className="glass-panel animate-slide-up" style={{ padding: '1.25rem 1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
      <div style={{
        width: 48, height: 48, borderRadius: 14, flexShrink: 0,
        background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={22} style={{ color }} />
      </div>
      <div>
        <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#fff', lineHeight: 1 }}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </div>
        <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.45)', marginTop: 4 }}>{label}</div>
        {sublabel && <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.25)', marginTop: 2 }}>{sublabel}</div>}
      </div>
    </div>
  )
}

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'rgba(15,15,25,0.95)', border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 10, padding: '0.6rem 0.9rem', fontSize: '0.82rem', color: '#fff',
    }}>
      <div style={{ color: 'rgba(255,255,255,0.5)', marginBottom: 4 }}>{label}</div>
      <div style={{ color: '#A78BFA', fontWeight: 700 }}>{payload[0]?.value} posts</div>
    </div>
  )
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.analytics.overview()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const statusPieData = data
    ? Object.entries(data.status_distribution)
        .filter(([, v]) => v > 0)
        .map(([name, value]) => ({ name, value }))
    : []

  const platformBarData = data
    ? Object.entries(data.platform_breakdown).map(([name, count]) => ({ name, count }))
    : []

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
        <div className="animate-slide-up" style={{ marginBottom: '2rem' }}>
          <h1 style={{
            fontSize: '1.75rem', fontWeight: 700, color: '#fff',
            background: 'linear-gradient(135deg, #fff 30%, rgba(255,255,255,0.5))',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>Analytics</h1>
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.875rem', marginTop: 4 }}>
            Real-time performance across all campaigns
          </p>
        </div>

        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '5rem 0' }}>
            <div style={{ display: 'flex', gap: 6 }}>
              <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
            </div>
          </div>
        ) : error ? (
          <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center', color: '#FCA5A5' }}>
            <AlertCircle size={32} style={{ margin: '0 auto 1rem' }} />
            <div style={{ fontWeight: 600 }}>Failed to load analytics</div>
            <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.4)', marginTop: 8 }}>{error}</div>
          </div>
        ) : data ? (
          <>
            {/* KPI Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
              <StatCard label="Total Campaigns" value={data.total_goals} icon={Target} color="#A78BFA" />
              <StatCard label="Completed" value={data.goals_completed} icon={CheckCircle2} color="#34D399" />
              <StatCard label="Executing Now" value={data.goals_executing} icon={Activity} color="#22D3EE" />
              <StatCard label="Awaiting Approval" value={data.goals_awaiting_approval} icon={AlertCircle} color="#FCD34D" />
              <StatCard label="Posts Published" value={data.total_posts_published} icon={Zap} color="#A78BFA" />
              <StatCard label="Total Reach" value={data.total_reach} icon={Globe} color="#34D399" />
              <StatCard
                label="Avg Engagement"
                value={`${(data.avg_engagement_rate * 100).toFixed(2)}%`}
                icon={TrendingUp} color="#F59E0B"
              />
              <StatCard label="Skills Created" value={data.skill_count} icon={Star} color="#22D3EE" />
              <StatCard label="Training Docs" value={data.training_doc_count} icon={BookOpen} color="#A78BFA" />
              <StatCard label="Media Assets" value={data.media_asset_count} icon={Image} color="#34D399" />
            </div>

            {/* Charts row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>

              {/* Posts per day line chart */}
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <BarChart2 size={16} style={{ color: '#A78BFA' }} /> Posts per Day (30 days)
                </div>
                {data.posts_per_day.some(d => d.count > 0) ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart data={data.posts_per_day}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                      <XAxis dataKey="date"
                        tickFormatter={d => d.slice(5)}
                        tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.35)' }}
                        interval={6}
                        axisLine={false} tickLine={false}
                      />
                      <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.35)' }}
                        axisLine={false} tickLine={false} />
                      <Tooltip content={<CustomTooltip />} />
                      <Line type="monotone" dataKey="count" stroke="#7C3AED"
                        strokeWidth={2} dot={false}
                        activeDot={{ r: 4, fill: '#A78BFA' }} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'rgba(255,255,255,0.2)', fontSize: '0.85rem' }}>
                    No posts published yet
                  </div>
                )}
              </div>

              {/* Platform breakdown bar chart */}
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Globe size={16} style={{ color: '#22D3EE' }} /> Campaigns by Platform
                </div>
                {platformBarData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={platformBarData} barSize={28}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                      <XAxis dataKey="name"
                        tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.4)' }}
                        axisLine={false} tickLine={false}
                      />
                      <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.35)' }}
                        axisLine={false} tickLine={false} />
                      <Tooltip
                        contentStyle={{ background: 'rgba(15,15,25,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10 }}
                        itemStyle={{ color: '#fff' }} labelStyle={{ color: 'rgba(255,255,255,0.5)' }}
                      />
                      <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                        {platformBarData.map((entry, index) => (
                          <Cell key={index} fill={PLATFORM_COLORS[entry.name] || '#A78BFA'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'rgba(255,255,255,0.2)', fontSize: '0.85rem' }}>
                    No campaign data yet
                  </div>
                )}
              </div>
            </div>

            {/* Status donut + engagement */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>

              {/* Status distribution */}
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1.25rem' }}>
                  Campaign Status Distribution
                </div>
                {statusPieData.length > 0 ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                    <ResponsiveContainer width={140} height={140}>
                      <PieChart>
                        <Pie data={statusPieData} cx="50%" cy="50%" innerRadius={40} outerRadius={65}
                          dataKey="value" paddingAngle={3}>
                          {statusPieData.map((entry, i) => (
                            <Cell key={i} fill={STATUS_COLORS[entry.name] || '#6B7280'} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {statusPieData.map((entry, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.82rem' }}>
                          <div style={{ width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                            background: STATUS_COLORS[entry.name] || '#6B7280' }} />
                          <span style={{ color: 'rgba(255,255,255,0.6)', flex: 1, textTransform: 'capitalize' }}>
                            {entry.name.replace('_', ' ')}
                          </span>
                          <span style={{ color: '#fff', fontWeight: 600 }}>{entry.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'rgba(255,255,255,0.2)', fontSize: '0.85rem' }}>
                    No campaigns yet
                  </div>
                )}
              </div>

              {/* Engagement summary */}
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <div style={{ fontWeight: 600, color: '#fff', marginBottom: '1.25rem' }}>
                  Total Engagement
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {[
                    { label: 'Impressions', value: data.total_impressions, color: '#A78BFA' },
                    { label: 'Likes', value: data.total_likes, color: '#34D399' },
                    { label: 'Comments', value: data.total_comments, color: '#22D3EE' },
                    { label: 'Shares', value: data.total_shares, color: '#F59E0B' },
                    { label: 'Total Reach', value: data.total_reach, color: '#FCA5A5' },
                  ].map(item => (
                    <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: item.color, flexShrink: 0 }} />
                      <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem', flex: 1 }}>{item.label}</span>
                      <span style={{ color: '#fff', fontWeight: 700, fontSize: '0.95rem' }}>
                        {item.value.toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        ) : null}
      </main>
    </div>
  )
}
