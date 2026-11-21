# AutoHeal DevOps — Enterprise Notification System Architecture

## 1. Executive Summary

The AutoHeal DevOps Enterprise Notification System provides an asynchronous, multi-channel alerting and dispatch platform designed for high-reliability SaaS environments. It decouples operational incident detection and automated healing actions from downstream delivery transports, ensuring zero interruption to core system reliability.

---

## 2. Architectural Design Principles

1. **Non-Blocking Delivery Guarantee**: Notification dispatches are executed either asynchronously via Celery background tasks or wrapped in isolated try/except blocks. Downstream SMTP network errors, Slack HTTP 5xx responses, or webhook timeouts **never** interrupt or fail incident creation or automated healing actions.
2. **Strict Multi-Tenant Isolation**: Every `NotificationChannel`, `NotificationSubscription`, and `NotificationDelivery` record is strictly scoped by `organization_id`. Database queries enforce tenant boundaries at the SQL level.
3. **Disabled-by-Default Security Baseline**: Newly created notification channels are disabled (`is_enabled=False`) until explicitly verified and activated by an authenticated Operator or Admin.
4. **Credential Protection & Masking**: Sensitive tokens (Slack webhook tokens, SMTP passwords, PagerDuty integration keys) are stored server-side only. Client API responses mask all credentials using `********`.
5. **Idempotency & Deduplication**: Outbound deliveries compute a deterministic SHA-256 idempotency key:
   $$\text{IdempotencyKey} = \text{SHA256}(\text{org\_id} : \text{channel\_id} : \text{event\_type} : \text{incident\_id} : \text{bucket})$$
   Duplicate events occurring within the deduplication window are suppressed without generating duplicate alerts.
6. **Exponential Backoff & Retries**: Failed deliveries transition to `retrying` and schedule subsequent retry intervals following exponential backoff:
   $$\text{Delay} = 5\text{s} \times 2^{\text{retry\_count}}$$
   Upon reaching `max_retries` (default: 3), the delivery transitions to `permanently_failed` without further network attempts.

---

## 3. Data Model Hierarchy

```
Organization
  ├── NotificationChannel (Email, Slack, Teams, Webhook)
  │     ├── NotificationSubscription (Filters: event_type, min_severity)
  │     └── NotificationDelivery (Delivery audit log, idempotency, retries)
  ├── WebhookEndpoint (Signed outbound webhooks with SSRF prevention)
  └── EscalationPolicy (Unacknowledged timeout rules and quiet hours)
```

---

## 4. Supported Notification Adapters

| Adapter | Target | Transport | Security Features |
|---|---|---|---|
| **Slack** | Channels, DMs | HTTPS POST (JSON) | Block Kit formatting, SSRF filtering, masked webhook URLs |
| **Microsoft Teams** | Office 365 Channels | HTTPS POST (JSON) | MessageCard formatting, theme coloring by severity |
| **Email (SMTP)** | Distribution Lists | STARTTLS (Port 587) | TLS encryption, sanitized plaintext + HTML templates |
| **Generic Webhook** | PagerDuty, Datadog, In-house | HTTPS POST (Raw JSON) | HMAC-SHA256 signature header, replay prevention timestamp |

---

## 5. Celery Worker Integration

Scheduled and background notification dispatches are managed via `app.tasks.notifications.dispatch_notification_task`:
- **Task Concurrency**: Worker-level concurrency with fair dispatching (`worker_prefetch_multiplier=1`).
- **Resilience**: Redis broker connection retries on boot, task late-acknowledgment (`task_acks_late=True`), and dead-letter failure logging.
