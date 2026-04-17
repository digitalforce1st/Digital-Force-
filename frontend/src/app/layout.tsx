import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Digital Force — Autonomous Social Media Agency',
  description: 'AI-powered autonomous social media intelligence. Give it a goal. Watch it work.',
  keywords: ['AI', 'social media', 'autonomous', 'digital marketing', 'content generation'],
}

import AuthGuard from '@/components/AuthGuard'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-surface text-white antialiased min-h-screen">
        <AuthGuard>
          {children}
        </AuthGuard>
      </body>
    </html>
  )
}
