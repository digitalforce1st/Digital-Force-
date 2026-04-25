export function generateStaticParams() {
  // Return a dummy placeholder. This creates a static shell HTML file at /training/default.html
  // which Cloudflare Pages will use as the SPA entry point.
  return [{ id: 'default' }]
}

export default function TrainingIdLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
