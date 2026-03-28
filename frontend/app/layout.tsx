import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Link2Context - From Link to Context',
  description: 'Turn any webpage into clean Markdown for your AI',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
