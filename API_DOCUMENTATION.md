# AutoHeal DevOps — REST API Documentation

Base URL: `http://localhost:8000/api/v1`

All responses use JSON format. Authenticated requests require the HTTP Header:
`Authorization: Bearer <jwt_access_token>`

---

## 1. Authentication Endpoints (`/api/v1/auth`)

### POST `/api/v1/auth/register`
Creates a new tenant user account and default organization.
* **Request Body**:
  ```json
  {
    "email": "operator@example.com",
    "password": "StrongPassword123!",
    "full_name": "Jane Operator",
    "organization_name": "Acme SRE"
  }
  ```
* **Response (201 Created)**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 900,
    "user": {
      "id": "uuid",
      "email": "operator@example.com",
      "full_name": "Jane Operator",
      "role": "operator",
      "organization_id": "uuid",
      "organization_name": "Acme SRE",
      "is_active": true
    }
  }
  ```

### POST `/api/v1/auth/login`
Authenticates user credentials and issues tokens.
* **Request Body**:
  ```json
  {
    "email": "operator@example.com",
    "password": "StrongPassword123!"
  }
  ```
* **Response (200 OK)**: Sets HttpOnly `refresh_token` cookie and returns `TokenResponse`.

### POST `/api/v1/auth/refresh`
Rotates refresh token and issues a fresh 15-minute JWT.
* **Cookie**: `refresh_token=<token>` (or JSON body `{"refresh_token": "..."}`)
* **Response (200 OK)**: `TokenResponse` with rotated tokens.

### POST `/api/v1/auth/logout`
Revokes active refresh token and clears session cookie.
* **Response (200 OK)**: `{"message": "Logged out successfully."}`

### GET `/api/v1/auth/me`
Returns current user profile and organization details.

---

## 2. Services Endpoints (`/api/v1/services`)

### GET `/api/v1/services`
Lists all monitored microservices within the user's organization.
* **Query Parameters**: `environment` (optional), `status` (optional).
* **Response (200 OK)**:
  ```json
  [
    {
      "id": "svc-api",
      "name": "checkout-api",
      "environment": "production",
      "status": "healthy",
      "availability": 99.98,
      "errorRate": 0.0,
      "latencyMs": 25,
      "lastChecked": "2026-11-21T05:04:00Z"
    }
  ]
  ```

### GET `/api/v1/services/{service_id}`
Returns real-time status and configuration for a specific microservice.

---

## 3. Alerts & Webhook Ingestion (`/api/v1/alerts`)

### POST `/api/v1/alerts/webhook`
Secure ingestion webhook for Prometheus Alertmanager.
* **Headers**: `Authorization: Bearer <secret>` or `X-Alertmanager-Secret: <secret>` or `X-AutoHeal-Signature: sha256=<hmac>`
* **Request Body (Alertmanager Webhook Schema)**:
  ```json
  {
    "version": "4",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "ServiceDown",
          "service": "checkout-api",
          "environment": "production",
          "severity": "critical"
        },
        "annotations": {
          "summary": "Service checkout-api is unreachable",
          "description": "Scrape checks failed for >30s",
          "probable_cause": "Container crash",
          "recommended_action": "restart_service"
        }
      }
    ]
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "processed_alerts": 1,
    "incidents_created": 1,
    "incidents_updated": 0,
    "details": ["Created new incident 'INC-1070' for service 'checkout-api'."]
  }
  ```

---

## 4. Incidents Endpoints (`/api/v1/incidents`)

### GET `/api/v1/incidents`
Lists all organization incidents with optional status or severity filters.
* **Query Parameters**: `status` (`open`, `investigating`, `recovering`, `resolved`), `severity` (`critical`, `high`, `medium`, `low`).

### GET `/api/v1/incidents/{incident_id}`
Retrieves complete incident detail including evidence list, timeline, and AI diagnosis.

### GET `/api/v1/incidents/{incident_id}/report`
Downloads cryptographically generated post-mortem report.
* **Query Parameters**: `format=pdf` (default) or `format=json`.
* **Response**: Binary PDF file (`application/pdf`) or structured JSON.

---

## 5. Recoveries Endpoints (`/api/v1/recoveries`)

### GET `/api/v1/recoveries`
Lists the recovery action queue and operation history.

### POST `/api/v1/recoveries/{recovery_id}/approve`
**Role Required**: `operator` or `admin`.
Submits human-in-the-loop approval for a proposed remediation action.

### POST `/api/v1/recoveries/{recovery_id}/reject`
**Role Required**: `operator` or `admin`.
Rejects a proposed remediation plan and records rejection audit.

### POST `/api/v1/recoveries/{recovery_id}/execute`
**Role Required**: `operator` or `admin`.
Triggers controlled execution of an approved recovery action and coordinates post-recovery verification.

---

## 6. Analytics Endpoints (`/api/v1/analytics`)

### GET `/api/v1/analytics/summary`
Returns mathematically rigorous platform SRE metrics:
```json
{
  "detectionLatencySeconds": 42.22,
  "recoveryDurationMinutes": 8.4,
  "recoverySuccessRate": 80.0,
  "falsePositiveRate": 0.0,
  "operatorRejectionRate": 20.0,
  "availability": 99.98,
  "incidentCount": 70,
  "history": [ ... ]
}
```

---

## 7. Real-Time SSE Stream (`/api/v1/events`)

### POST `/api/v1/events/ticket`
Generates a short-lived, single-use ticket for SSE connection authentication:
* **Response**: `{"ticket": "opaque_string", "expires_in": 60}`

### GET `/api/v1/events/stream?ticket=<ticket>`
Streams Server-Sent Events (SSE) to organization dashboards for real-time state synchronization.
Events: `incident_created`, `incident_updated`, `recovery_updated`, `service_health`.
