import { NextRequest, NextResponse } from 'next/server'

// Cloudflare Pages requires all middleware to run on the Edge Runtime
export const runtime = 'edge'

const PUBLIC_PATHS = ['/login', '/landing', '/api', '/_next', '/favicon.ico']

/**
 * Next.js Edge Middleware — authenticates all private routes.
 * Checks the df_token cookie set at login and redirects to /login if missing.
 */
export function middleware(request: NextRequest) {
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
