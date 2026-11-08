'use client'

import { useState, type FormEvent } from 'react'
import Link from 'next/link'
import { ArrowLeft, ArrowRight, LockKeyhole } from 'lucide-react'
import { Brand } from '@/components/marketing/brand'

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const [message, setMessage] = useState('')
  const isRegister = mode === 'register'

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('Authentication is not part of the supplied FastAPI contract. No credentials were sent or stored. Connect a real identity provider before using this flow.')
  }

  return <main className="auth-page">
    <section className="auth-aside"><div><Brand /></div><div><div className="status-pill"><span className="pulse" /> CONTROLLED DEVOPS AUTOMATION</div><h1>Good operations start with clear signals.</h1><p>Monitor service health, understand incidents, and keep recovery actions within your team&apos;s control.</p></div><Link href="/" className="feature-more"><ArrowLeft size={13} /> Back to AutoHeal</Link></section>
    <section className="auth-main"><form className="auth-form" onSubmit={handleSubmit}>
      <span className="section-kicker">{isRegister ? 'Create workspace' : 'Welcome back'}</span>
      <h2 style={{ marginTop: 12 }}>{isRegister ? 'Get started with AutoHeal' : 'Sign in to your workspace'}</h2>
      <p>{isRegister ? 'Create your workspace to explore the product preview.' : 'Use your team account to continue.'}</p>
      <div className="notice-strip" style={{ marginBottom: 12 }}><strong style={{ color: '#dedaff' }}>Frontend preview only.</strong> Authentication is not connected yet. No password is sent or saved.</div>
      {isRegister && <><label htmlFor="full-name">Full name</label><input id="full-name" name="name" type="text" autoComplete="name" placeholder="Alex Morgan" required /></>}
      <label htmlFor="email">Work email</label><input id="email" name="email" type="email" autoComplete="email" placeholder="you@company.com" required />
      <label htmlFor="password">Password</label><input id="password" name="password" type="password" autoComplete={isRegister ? 'new-password' : 'current-password'} placeholder="At least 8 characters" minLength={8} required />
      <button className="btn btn-primary" type="submit">{isRegister ? 'Create account' : 'Sign in'} <ArrowRight size={14} /></button>
      {message && <div className="auth-message" role="status">{message}</div>}
      <div className="auth-switch">{isRegister ? 'Already have an account?' : 'New to AutoHeal?'}{' '}{isRegister ? <Link href="/login">Sign in</Link> : <Link href="/register">Create an account</Link>}</div>
      <div className="auth-switch" style={{ marginTop: 26 }}><LockKeyhole size={11} style={{ verticalAlign: 'middle', marginRight: 5 }} /> Secure authentication will be provided by the connected backend.</div>
    </form></section>
  </main>
}
