# AutoHeal DevOps — AI Provider Reliability & Fallback

## Overview
Production autonomous systems cannot depend on external LLM availability. When network partitions, API rate limits (HTTP 429), or cloud provider outages occur, AutoHeal maintains continuous, deterministic operation.

## Reliability Mechanisms

### 1. Bounded Request Timeouts
Calls to Google Gemini API are bounded by a configurable timeout (default 15.0s, hard capped at 30.0s). If the API fails to respond within the window, the request is aborted immediately to prevent thread exhaustion.

### 2. Retries with Exponential Backoff
For transient errors (HTTP 429 Too Many Requests, HTTP 5xx Server Errors, or network drops), the provider attempts a maximum of 2 requests with exponential backoff:
$$\text{delay} = 1.0\text{s} \times \text{attempt}$$

### 3. Transparent Heuristic Fallback
If external AI calls fail or if `AI_API_KEY` is omitted, the system transparently falls back to the `HeuristicDiagnosisProvider`:
- Deterministic, rule-based expert engine mapping observed telemetry to allowlisted actions.
- Explicitly sets `provider_source="heuristic_fallback"` in all diagnostics and database records.
- Zero downtime; operational workflow continues uninterrupted.

### 4. Recovery Allowlist Enforcement
Every diagnosis result is checked against the strict recovery action allowlist:
- `restart_service`
- `clear_cache`
- `scale_service`
- `restore_health`
- `rollback_release`

If an unapproved action is suggested by external AI, the engine automatically replaces it with the safe default `restart_service` and logs a security warning.
