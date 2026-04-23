export function generateStaticParams() {
  // Return a dummy placeholder. This creates a static shell HTML file at /training/[id].html
  // which Cloudflare Pages will use as the SPA entry point.
  return [{ id: '[id]' }]
}

export default function TrainingIdLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
