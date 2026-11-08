import Link from 'next/link'
import { Activity, ArrowUpRight } from 'lucide-react'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" href="/" aria-label="AutoHeal DevOps home">
      <span className="brand-mark" aria-hidden="true"><Activity size={16} strokeWidth={2.2} /></span>
      {!compact && <span>autoheal<span style={{ color: '#35d6c5' }}>.</span>devops</span>}
    </Link>
  )
}

export function ArrowLink({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link className="btn btn-secondary" href={href}>{children}<ArrowUpRight size={14} aria-hidden="true" /></Link>
}
