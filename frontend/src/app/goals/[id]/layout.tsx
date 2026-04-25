export function generateStaticParams() {
  // Return a dummy placeholder. This creates a static shell HTML file at /goals/default.html
  // and /goals/default/approve.html which Cloudflare Pages will use as the SPA entry point.
  return [{ id: 'default' }]
}

export default function GoalsIdLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
