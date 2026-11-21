# AutoHeal DevOps — Vercel Frontend to Backend Connection Guide

This document provides a step-by-step walkthrough for connecting the live Vercel frontend (`https://autoheal-omega.vercel.app`) to your deployed AutoHeal FastAPI backend.

---

## 1. Problem Statement & Root Cause

### What the User Sees
When visiting the login page at `https://autoheal-omega.vercel.app/login`, the user is greeted with the informational warning:
```text
FastAPI preview. Set NEXT_PUBLIC_API_BASE_URL to authenticate against the backend.
```
In this state, entering credentials fails because no backend API URL has been configured in the Vercel build environment, and production builds strictly refuse to use simulated fallback data.

### Root Cause
`NEXT_PUBLIC_API_BASE_URL` is undefined or empty in the Vercel project environment variables. As a result:
1. `isApiConfigured` evaluates to `false`.
2. Requests cannot be dispatched to FastAPI endpoints (`/api/v1/auth/login`, `/api/v1/auth/register`).
3. The UI warns the operator that a backend connection is required.

---

## 2. Step-by-Step Connection Instructions

### Step 1: Obtain Your Deployed Backend URL
Deploy your backend using Render, Railway, or Fly.io (see [BACKEND_DEPLOYMENT.md](./BACKEND_DEPLOYMENT.md)).
Copy the resulting public HTTPS URL, for example:
```text
https://autoheal-backend-xxxx.onrender.com
```

### Step 2: Configure Environment Variables in Vercel
1. Log in to your [Vercel Dashboard](https://vercel.com).
2. Select the **`autoheal-omega`** project (or your deployed AutoHeal project).
3. Navigate to **Settings** > **Environment Variables**.
4. Add the following variable:
   - **Key**: `NEXT_PUBLIC_API_BASE_URL`
   - **Value**: `https://autoheal-backend-xxxx.onrender.com` (use your actual backend URL)
   - **Environments**: Check **Production**, **Preview**, and **Development**.
5. *(Optional)* If demo mode is desired for previewing UI without backend services:
   - **Key**: `NEXT_PUBLIC_DEMO_MODE`
   - **Value**: `false` (ensure this is `false` for real production authentication)
6. Click **Save**.

### Step 3: Trigger a Redeployment on Vercel
Because Next.js inlines `NEXT_PUBLIC_*` environment variables during compilation at build time, updating environment variables requires a new deployment:
1. Go to the **Deployments** tab in your Vercel project.
2. Click the three dots menu (**...**) on the latest deployment.
3. Select **Redeploy**.
4. Check **Redeploy with existing build cache** (or rebuild without cache if needed) and click **Redeploy**.

---

## 3. Backend CORS & Cookie Configuration

For the Vercel frontend to successfully communicate with the backend, the backend must be configured to accept cross-origin requests and credentials.

### Backend Environment Variables
In your backend hosting dashboard (e.g., Render or Railway), ensure these variables are set:

```ini
# Explicitly whitelist the Vercel domain (must include protocol and no trailing slash)
CORS_ORIGINS=["https://autoheal-omega.vercel.app"]

# Cross-Site Cookie Settings (Required for cross-domain auth cookies)
COOKIE_SECURE=true
COOKIE_SAMESITE=none
COOKIE_DOMAIN=
```

### Explanation of Settings:
- **`CORS_ORIGINS`**: The browser blocks API requests from `https://autoheal-omega.vercel.app` unless the backend responds with `Access-Control-Allow-Origin: https://autoheal-omega.vercel.app` and `Access-Control-Allow-Credentials: true`.
- **`COOKIE_SECURE=true`**: Required by modern browsers whenever `SameSite=None` is set.
- **`COOKIE_SAMESITE=none`**: Allows the browser to send the `refresh_token` HttpOnly cookie on cross-site requests from `autoheal-omega.vercel.app` to your backend domain.

---

## 4. Frontend Connection Verification Checklist

Once the redeployment completes, verify the connection end-to-end:

| Step | Action | Expected Result |
| :--- | :--- | :--- |
| **1. UI Status Banner** | Open `https://autoheal-omega.vercel.app/login` | The amber "FastAPI preview" banner is replaced by: `"Connected to AutoHeal API. Secured with Argon2id hashing and JWT access tokens."` |
| **2. Account Registration** | Click **Create Account**, fill in Name, Organization, Work Email, and Password | Registration succeeds, user account and organization are created in PostgreSQL, and user is redirected to the dashboard. |
| **3. User Sign In** | Sign out and sign back in with credentials | JWT access token is stored in memory/localStorage, and `refresh_token` cookie is set. Redirects to `/overview`. |
| **4. Protected API Calls** | Navigate to **Services** and **Incidents** | Live services and incident logs load cleanly without 401 or CORS errors in the browser console. |
| **5. Token Refresh (RTR)** | Wait or inspect Network tab during token refresh | Request to `/api/v1/auth/refresh` succeeds and returns a new access token without requiring re-login. |
| **6. User Sign Out** | Click user avatar > **Sign out** | Access token is cleared, refresh token is revoked on backend, and user is redirected to `/login`. |

---

## 5. Troubleshooting Common Connection Issues

### Issue 1: "CORS request did not succeed" or `Access-Control-Allow-Origin` error
- **Cause**: Backend `CORS_ORIGINS` does not match the frontend domain exactly.
- **Fix**: Check `CORS_ORIGINS` in your backend environment variables. It must be a valid JSON array containing `"https://autoheal-omega.vercel.app"`.

### Issue 2: "Backend unreachable. Unable to reach the configured API server."
- **Cause**: The backend container is down, sleeping (Render free tier spin-up delay), or the URL is mistyped.
- **Fix**: Open the backend health URL (`https://your-backend.onrender.com/api/v1/health`) in your browser. Verify it returns `{"status":"healthy"}` before testing the frontend.

### Issue 3: Refresh token cookie not saved or sent
- **Cause**: `COOKIE_SAMESITE` is set to `lax` or `strict` instead of `none`, or `COOKIE_SECURE` is `false`.
- **Fix**: Set `COOKIE_SAMESITE=none` and `COOKIE_SECURE=true` in backend environment variables.
