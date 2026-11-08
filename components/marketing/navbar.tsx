'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Menu, X } from 'lucide-react'
import { Brand } from './brand'

const links = [
  { label: 'Platform', href: '#platform' },
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#workflow' },
  { label: 'Integrations', href: '#integrations' },
  { label: 'Security', href: '#security' },
]

export function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState('#platform')

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 16)
    update()
    window.addEventListener('scroll', update, { passive: true })
    return () => window.removeEventListener('scroll', update)
  }, [])

  useEffect(() => {
    const sections = links.map((link) => document.querySelector(link.href)).filter((section): section is Element => Boolean(section))
    const observer = new IntersectionObserver((entries) => {
      const current = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
      if (current) setActive(`#${current.target.id}`)
    }, { rootMargin: '-18% 0px -68% 0px', threshold: 0 })
    sections.forEach((section) => observer.observe(section))
    return () => observer.disconnect()
  }, [])

  return (
    <header className={`nav-shell${scrolled ? ' scrolled' : ''}`}>
      <div className="site-container nav-inner">
        <Brand />
        <nav className="nav-links" aria-label="Main navigation">
          {links.map((link) => <a key={link.href} href={link.href} className={active === link.href ? 'active' : undefined} aria-current={active === link.href ? 'location' : undefined}>{link.label}</a>)}
        </nav>
        <div className="nav-actions">
          <Link className="btn btn-quiet sign-in" href="/login">Sign in</Link>
          <Link className="btn btn-primary" href="/register">Get started</Link>
          <button className="nav-mobile-toggle" aria-label={open ? 'Close navigation' : 'Open navigation'} aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? <X size={17} /> : <Menu size={17} />}
          </button>
        </div>
      </div>
      {open && <nav className="mobile-menu" aria-label="Mobile navigation">
        {links.map((link) => <a key={link.href} href={link.href} className={active === link.href ? 'active' : undefined} aria-current={active === link.href ? 'location' : undefined} onClick={() => setOpen(false)}>{link.label}</a>)}
        <Link href="/login" onClick={() => setOpen(false)}>Sign in</Link>
      </nav>}
    </header>
  )
}
