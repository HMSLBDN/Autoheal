'use client'

import { useEffect, useRef } from 'react'
import { API_BASE_URL, getAccessToken, isApiConfigured } from './client'

export type EventCallback<T = unknown> = (data: T) => void

export interface RealtimeHandlers {
  onIncidentCreated?: EventCallback<{ id: string; title: string; serviceName: string; severity: string; status: string }>
  onIncidentUpdated?: EventCallback<{ id: string; status?: string; recoveryStatus?: string; severity?: string }>
  onRecoveryUpdated?: EventCallback<{ id: string; status?: string; verification?: string; durationSeconds?: number }>
  onServiceHealth?: EventCallback<{ id: string; name: string; status: string; availability: number; errorRate: number; latencyMs: number }>
}

/**
 * Connects to the authenticated Server-Sent Events (SSE) endpoint:
 * /api/v1/events/stream?token=<access_token>
 * Automatically manages connection retries with exponential backoff,
 * handles token expiration, and dispatches real-time domain events.
 */
export function useRealtimeEvents(handlers: RealtimeHandlers, enabled = true) {
  const handlersRef = useRef(handlers)

  useEffect(() => {
    handlersRef.current = handlers
  }, [handlers])

  useEffect(() => {
    if (!enabled || !isApiConfigured || typeof window === 'undefined') return

    let eventSource: EventSource | null = null
    let retryTimeout: ReturnType<typeof setTimeout> | undefined
    let retryDelay = 1000
    let isDisposed = false

    async function connect() {
      if (isDisposed) return

      const token = getAccessToken()
      if (!token) {
        // Not authenticated yet, retry later
        retryTimeout = setTimeout(connect, 3000)
        return
      }

      let streamUrl = `${API_BASE_URL}/api/v1/events/stream?token=${encodeURIComponent(token)}`

      // Hardened SSE authentication: request short-lived single-use ticket to prevent JWT leakage in access logs
      try {
        const ticketRes = await fetch(`${API_BASE_URL}/api/v1/events/ticket`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          credentials: 'include',
        })
        if (ticketRes.ok) {
          const ticketData = await ticketRes.json()
          if (ticketData?.ticket) {
            streamUrl = `${API_BASE_URL}/api/v1/events/stream?ticket=${encodeURIComponent(ticketData.ticket)}`
          }
        }
      } catch {
        // Fall back to direct stream connection
      }

      if (isDisposed) return

      try {
        eventSource = new EventSource(streamUrl, { withCredentials: true })

        eventSource.onopen = () => {
          retryDelay = 1000 // Reset backoff on successful handshake
        }

        eventSource.addEventListener('incident_created', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            handlersRef.current.onIncidentCreated?.(data)
          } catch {}
        })

        eventSource.addEventListener('incident_updated', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            handlersRef.current.onIncidentUpdated?.(data)
          } catch {}
        })

        eventSource.addEventListener('recovery_updated', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            handlersRef.current.onRecoveryUpdated?.(data)
          } catch {}
        })

        eventSource.addEventListener('service_health', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            handlersRef.current.onServiceHealth?.(data)
          } catch {}
        })

        eventSource.onerror = () => {
          if (eventSource) {
            eventSource.close()
            eventSource = null
          }
          if (!isDisposed) {
            // Reconnect with exponential backoff capped at 10s
            retryTimeout = setTimeout(connect, retryDelay)
            retryDelay = Math.min(retryDelay * 1.5, 10000)
          }
        }
      } catch {
        if (!isDisposed) {
          retryTimeout = setTimeout(connect, 5000)
        }
      }
    }

    connect()

    return () => {
      isDisposed = true
      if (retryTimeout) clearTimeout(retryTimeout)
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }
    }
  }, [enabled])
}
