export function generateStaticParams() {
  // Return a dummy placeholder. This creates a static shell HTML file at /goals/[id].html
  // and /goals/[id]/approve.html which Cloudflare Pages will use as the SPA entry point.
  return [{ id: '[id]' }]
}

export default function GoalsIdLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
