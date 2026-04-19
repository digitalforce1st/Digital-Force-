'use client'

import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import VoiceInterface from '@/components/VoiceInterface'

export default function GlobalVoice() {
  const pathname = usePathname()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted || !pathname) return null

  const PUBLIC_PATHS = ['/login', '/landing', '/api', '/_next']
  if (PUBLIC_PATHS.some(p => pathname.startsWith(p)) || pathname === '/' || pathname === '/favicon.ico') {
    return null
  }

  return <VoiceInterface />
}
