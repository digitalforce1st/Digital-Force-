'use client'

import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { getToken } from '@/lib/auth'

const PUBLIC_PATHS = ['/login', '/landing', '/api', '/_next']

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [authorized, setAuthorized] = useState(false)

  useEffect(() => {
    // Check if the current path is public
    if (PUBLIC_PATHS.some(p => pathname.startsWith(p)) || pathname === '/' || pathname === '/favicon.ico') {
      setAuthorized(true)
      return
    }

    // Check for auth token using the same function that sets it
    const token = getToken()
    
    // Also check standard cookie in case the server set it and localStorage is empty
    const hasCookie = document.cookie.includes('df_token')

    if (!token && !hasCookie) {
      setAuthorized(false)
      const loginUrl = `/login?from=${encodeURIComponent(pathname)}`
      router.push(loginUrl)
    } else {
      setAuthorized(true)
    }
  }, [pathname, router])

  // Prevent flash of protected content before redirect
  if (!authorized && !PUBLIC_PATHS.some(p => pathname.startsWith(p)) && pathname !== '/' && pathname !== '/favicon.ico') {
    return (
      <div style={{ display: 'flex', minHeight: '100vh', background: '#080B12', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" />
        </div>
      </div>
    )
  }

  return <>{children}</>
}
