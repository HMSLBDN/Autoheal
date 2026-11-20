'use client'

import { useState, type FormEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, ArrowRight, LockKeyhole } from 'lucide-react'
import { Brand } from '@/components/marketing/brand'
import { isApiConfigured } from '@/lib/api/client'
import { authApi } from '@/lib/api/resources'

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const router = useRouter()
  const [message, setMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const isRegister = mode === 'register'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('')
    setIsSubmitting(true)

    const form = event.currentTarget
    const formData = new FormData(form)
    const email = String(formData.get('email') ?? '').trim()
    const password = String(formData.get('password') ?? '')
    const fullName = String(formData.get('name') ?? '').trim()

    try {
      if (isApiConfigured) {
        if (isRegister) {
          await authApi.register(email, password, fullName || 'Operator')
        } else {
          await authApi.login(email, password)
        }
        router.push('/dashboard')
      } else {
        // Fallback when NEXT_PUBLIC_API_BASE_URL is not set
        setMessage('Backend API URL is not configured. Set NEXT_PUBLIC_API_BASE_URL in environment variables to connect to the FastAPI authentication backend.')
      }
    } catch (err) {
      const errMessage = err instanceof Error ? err.message : 'Authentication failed. Please check your credentials.'
      setMessage(errMessage)
    } finally {
      setIsSubmitting(false)
    }
  }

  return <main className="auth-page">
    <section className="auth-aside"><div><Brand /></div><div><div className="status-pill"><span className="pulse" /> CONTROLLED DEVOPS AUTOMATION</div><h1>Good operations start with clear signals.</h1><p>Monitor service health, understand incidents, and keep recovery actions within your team&apos;s control.</p></div><Link href="/" className="feature-more"><ArrowLeft size={13} /> Back to AutoHeal</Link></section>
    <section className="auth-main"><form className="auth-form" onSubmit={handleSubmit}>
      <span className="section-kicker">{isRegister ? 'Create workspace' : 'Welcome back'}</span>
      <h2 style={{ marginTop: 12 }}>{isRegister ? 'Get started with AutoHeal' : 'Sign in to your workspace'}</h2>
      <p>{isRegister ? 'Create your workspace to explore the product preview.' : 'Use your team account to continue.'}</p>
      <div className="notice-strip" style={{ marginBottom: 12 }}>
        <strong style={{ color: '#dedaff' }}>{isApiConfigured ? 'Connected to AutoHeal API.' : 'FastAPI preview.'}</strong> {isApiConfigured ? 'Secured with Argon2id hashing and JWT access tokens.' : 'Set NEXT_PUBLIC_API_BASE_URL to authenticate against the backend.'}
      </div>
      {isRegister && <><label htmlFor="full-name">Full name</label><input id="full-name" name="name" type="text" autoComplete="name" placeholder="Alex Morgan" required disabled={isSubmitting} /></>}
      <label htmlFor="email">Work email</label><input id="email" name="email" type="email" autoComplete="email" placeholder="you@company.com" required disabled={isSubmitting} />
      <label htmlFor="password">Password</label><input id="password" name="password" type="password" autoComplete={isRegister ? 'new-password' : 'current-password'} placeholder="At least 8 characters" minLength={8} required disabled={isSubmitting} />
      <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? (isRegister ? 'Creating account...' : 'Signing in...') : (isRegister ? 'Create account' : 'Sign in')} <ArrowRight size={14} />
      </button>
      {message && <div className="auth-message" role="status">{message}</div>}
      <div className="auth-switch">{isRegister ? 'Already have an account?' : 'New to AutoHeal?'}{' '}{isRegister ? <Link href="/login">Sign in</Link> : <Link href="/register">Create an account</Link>}</div>
      <div className="auth-switch" style={{ marginTop: 26 }}><LockKeyhole size={11} style={{ verticalAlign: 'middle', marginRight: 5 }} /> Protected by Argon2id password hashing and JWT token rotation.</div>
    </form></section>
  </main>
}
