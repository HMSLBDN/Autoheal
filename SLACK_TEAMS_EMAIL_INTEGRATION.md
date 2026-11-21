# AutoHeal DevOps — Slack, Teams & Email Integration Guide

## 1. Overview

AutoHeal DevOps supports enterprise alerting across Slack, Microsoft Teams, and Email (SMTP). This guide outlines the payload formatting, credential handling, and configuration endpoints for each supported adapter.

---

## 2. Slack Webhook Integration

### Formatting Standard: Block Kit
Slack alerts use Slack's modern Block Kit structure with Markdown formatting:
- **Header Block**: Indicates incident severity and title (`[CRITICAL] Elevated API error rate on checkout-api`).
- **Section Block (Metadata)**: Multi-column fields showing Service, Severity, Current Status, and Incident ID.
- **Section Block (Diagnosis & Action)**: Highlights AI-recommended remediations and evidence summary.

### Configuration Payload
```json
{
  "name": "Production Incident Slack",
  "channelType": "slack",
  "isEnabled": true,
  "config": {
    "webhook_url": "https://example.com/webhook/slack-incoming"
  },
  "rateLimitPerMinute": 30
}
```

---

## 3. Microsoft Teams Integration

### Formatting Standard: MessageCard JSON
Microsoft Teams incoming webhooks accept MessageCard format:
- **Theme Color**: Automatically toggles dynamically based on incident severity:
  - `CRITICAL`: `#D63535` (Crimson red)
  - `HIGH`: `#F59E0B` (Amber)
  - `MEDIUM` / `LOW`: `#35D6C5` (AutoHeal Teal)
- **Sections & Facts**: Formats incident properties (Severity, Status, Incident ID, Recommended Action) as structured Teams Fact pairs.

### Configuration Payload
```json
{
  "name": "SRE Incident Operations Teams",
  "channelType": "teams",
  "isEnabled": true,
  "config": {
    "webhook_url": "https://outlook.office.com/webhook/..."
  },
  "rateLimitPerMinute": 30
}
```

---

## 4. Email (SMTP) Integration

### Formatting Standard: Dual-Mode MIME
Sends both plaintext and responsive HTML content:
- **Security**: Requires TLS/STARTTLS authentication on port 587 or 465.
- **Header Sanitization**: Prevents header injection attacks by escaping subject lines and recipient lists.
- **Templates**: Contains service metadata, telemetry deltas, direct links to the incident dashboard, and operator triage guidelines.

### Configuration Payload
```json
{
  "name": "Executive Incident Distribution",
  "channelType": "email",
  "isEnabled": false,
  "config": {
    "smtp_host": "smtp.sendgrid.net",
    "smtp_port": 587,
    "smtp_user": "apikey",
    "smtp_pass": "SG.xxxxxxxxxxxx",
    "recipients": "sre-alerts@acme.com, leads@acme.com"
  },
  "rateLimitPerMinute": 10
}
```

---

## 5. Security & Masking
When inspecting configured channels via `GET /api/v1/notifications/channels`, all sensitive tokens, passwords, and webhook URLs are masked server-side in `configMasked`:
```json
{
  "id": "c1f7b022-...",
  "name": "Production Incident Slack",
  "channelType": "slack",
  "isEnabled": true,
  "configMasked": {
    "webhook_url": "https://example.com/webhook/slack-incoming"
  },
  "rateLimitPerMinute": 30
}
```
Cleartext credentials are never leaked to client bundles or frontend state.
