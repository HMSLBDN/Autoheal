'use client'

import { useState, useEffect, type FormEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, ArrowRight, LockKeyhole } from 'lucide-react'
import { Brand } from '@/components/marketing/brand'
import { isApiConfigured, ApiError } from '@/lib/api/client'
import { authApi, healthApi } from '@/lib/api/resources'

type ConnectionState = 'not_configured' | 'checking' | 'connected' | 'unreachable'

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const router = useRouter()
  const [message, setMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionState>(
    isApiConfigured ? 'checking' : 'not_configured'
  )
  const isRegister = mode === 'register'

  useEffect(() => {
    if (!isApiConfigured) {
      return
    }

    let isMounted = true
    const controller = new AbortController()

    async function checkBackend() {
      try {
        await healthApi.get(controller.signal)
        if (isMounted) setConnectionStatus('connected')
      } catch {
        if (isMounted) setConnectionStatus('unreachable')
      }
    }

    checkBackend()

    return () => {
      isMounted = false
      controller.abort()
    }
  }, [])

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
        setMessage('Backend not configured: Set NEXT_PUBLIC_API_BASE_URL in your hosting environment variables to connect.')
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 0 || err.status === 408) {
          setConnectionStatus('unreachable')
          setMessage('Backend unreachable: Could not connect to the AutoHeal backend API. Verify the server is running and accessible.')
        } else if (err.status === 401) {
          setMessage('Authentication failure: Invalid work email or password.')
        } else if (err.status === 403) {
          setMessage('Authentication failure: Account access is restricted or deactivated.')
        } else {
          setMessage(err.message)
        }
      } else {
        const errMessage = err instanceof Error ? err.message : 'Authentication failed. Please check your credentials.'
        setMessage(errMessage)
      }
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
        {connectionStatus === 'not_configured' && (
          <>
            <strong style={{ color: '#dedaff' }}>FastAPI preview.</strong> Set NEXT_PUBLIC_API_BASE_URL to authenticate against the backend.
          </>
        )}
        {connectionStatus === 'checking' && (
          <>
            <strong style={{ color: '#dedaff' }}>Checking API connection...</strong> Contacting the AutoHeal FastAPI backend.
          </>
        )}
        {connectionStatus === 'connected' && (
          <>
            <strong style={{ color: '#dedaff' }}>Connected to AutoHeal API.</strong> Secured with Argon2id hashing and JWT access tokens.
          </>
        )}
        {connectionStatus === 'unreachable' && (
          <>
            <strong style={{ color: '#fca5a5' }}>Backend unreachable.</strong> Unable to reach the configured API server. Check server status and network connectivity.
          </>
        )}
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
