# AutoHeal DevOps — Outbound Webhook Security Guide

## 1. Threat Model & Security Posture

Outbound webhooks allow AutoHeal to push real-time alerts to downstream consumer systems (PagerDuty, Datadog, customer microservices). Because outbound webhooks trigger HTTP requests to user-provided URLs, they are vulnerable to two primary attack vectors:
1. **Server-Side Request Forgery (SSRF)**: Malicious operators or attackers targeting internal infrastructure, loopback endpoints, or cloud metadata services.
2. **Replay & Tampering Attacks**: Intercepted payloads replayed against downstream consumers or modified in transit.

AutoHeal implements an end-to-end defense-in-depth model to mitigate both vulnerabilities.

---

## 2. SSRF Protection Architecture (`app.services.enterprise.ssrf`)

Every webhook destination URL undergoes strict validation prior to dispatch:

### 1. Scheme Whitelisting
- Only `https://` is permitted in production environments.
- Unencrypted `http://`, `ftp://`, or `file://` schemes are rejected immediately with HTTP 400.

### 2. Forbidden Hostnames
Known cloud metadata endpoints are rejected before DNS resolution:
- `metadata.google.internal` (GCP)
- `169.254.169.254` (AWS EC2 / Azure)
- `instance-data` (OpenStack)

### 3. DNS Resolution & Subnet Filtering
Hostnames are resolved to IP addresses (both IPv4 and IPv6) via `socket.getaddrinfo`. Every resolved IP address is verified against forbidden subnets:
- **Loopback**: `127.0.0.0/8`, `::1/128`
- **RFC 1918 Private**: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- **Link-Local & Cloud Metadata**: `169.254.0.0/16`, `fe80::/10`
- **Carrier-Grade NAT & Multicast**: `100.64.0.0/10`, `224.0.0.0/4`
- **Current Network & Reserved**: `0.0.0.0/8`, `240.0.0.0/4`, `255.255.255.255/32`

If any resolved IP falls within a restricted range, the destination is rejected.

---

## 3. HMAC-SHA256 Cryptographic Signatures

Every outbound webhook includes cryptographic proof of authenticity and timestamp freshness in HTTP headers:

| Header | Description | Example |
|---|---|---|
| `X-AutoHeal-Delivery` | Unique UUID for delivery deduplication | `b8543478-f716-411a-8bb7-e0fa951667b9` |
| `X-AutoHeal-Timestamp` | Epoch timestamp of dispatch | `1732185600` |
| `X-AutoHeal-Signature` | Hex-encoded HMAC-SHA256 signature | `sha256=a1b2c3d4...` |

### Signature Generation Formula
$$\text{Signature} = \text{HMAC-SHA256}(\text{SecretToken}, \text{Timestamp} + "." + \text{RawBodyBytes})$$

---

## 4. Consumer Verification Implementation

Downstream receivers should verify the signature and reject replayed requests outside the timestamp skew window:

```python
import hmac
import hashlib
import time

def verify_autoheal_webhook(secret: str, signature_header: str, timestamp_header: str, raw_body: bytes) -> bool:
    # 1. Replay prevention: reject requests older than 300 seconds
    now = int(time.time())
    ts = int(timestamp_header)
    if abs(now - ts) > 300:
        return False  # Stale timestamp or replay attack

    # 2. Compute expected HMAC
    expected_sig = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        f"{timestamp_header}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    # 3. Constant-time comparison
    return hmac.compare_digest(expected_sig, signature_header)
```

The verification endpoint `POST /api/v1/webhooks/verify` is available in AutoHeal for testing and client integration checks.
