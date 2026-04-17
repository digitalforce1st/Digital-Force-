import { NextRequest, NextResponse } from 'next/server'

// Next.js 16 requires 'experimental-edge' for the proxy/middleware runtime
export const runtime = 'experimental-edge'

const PUBLIC_PATHS = ['/login', '/landing', '/api', '/_next', '/favicon.ico']

/**
 * Next.js 16 Proxy (renamed from middleware) — authenticates all private routes.
 * Checks the df_token cookie set at login and redirects to /login if missing.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Allow public paths through without auth check
  if (PUBLIC_PATHS.some(p => pathname.startsWith(p))) {
    return NextResponse.next()
  }

  // Check for token in cookies (set alongside localStorage at login)
  const token = request.cookies.get('df_token')?.value

  if (!token) {
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('from', pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)'],
}
