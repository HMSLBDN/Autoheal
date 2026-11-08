import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: {
    default: 'AutoHeal DevOps — Detect. Diagnose. Recover. Verify.',
    template: '%s | AutoHeal DevOps',
  },
  description: 'An AI-assisted DevOps platform for evidence-led incident diagnosis, controlled recovery, and verified service health.',
  applicationName: 'AutoHeal DevOps',
  keywords: ['DevOps', 'incident management', 'recovery automation', 'infrastructure monitoring'],
  icons: { icon: '/icon.svg' },
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#080b12',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
