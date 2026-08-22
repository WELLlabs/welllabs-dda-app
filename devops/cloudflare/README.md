# Cloudflare Worker error 1101 — blocks all sign-in and POST API calls

## Symptom

- **Sign in with Google** or **email/password login** fails
- Browser shows **Error 1101: Worker threw exception** (Cloudflare HTML page)
- Manual sign-in, create project, and any **POST** to `/wst/api/*` fails
- **GET** requests to the same API paths still work (e.g. `/wst/api/accounts/auth/me` → 401)

## Cause

A **Cloudflare Worker** attached to `ai.welllabs.org` crashes on **POST** requests to `/wst/api/*`.
The app now uses **`/wst/backend/*`** for all browser API calls to bypass this Worker.
The origin (nginx + FastAPI on EC2) is healthy.

This is **not** fixable in application code alone — the Worker must be disabled, fixed, or bypassed
in the Cloudflare dashboard.

## Fix (choose one)

### Option A — Remove the Worker route (fastest)

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Select the zone for **welllabs.org**
3. Go to **Workers & Pages** → **Overview** (or **Workers Routes**)
4. Find routes matching `ai.welllabs.org` or `ai.welllabs.org/*`
5. **Delete** those routes (or disable the Worker)

Wait ~1 minute, then retry sign-in.

### Option B — Replace with a safe passthrough Worker

Deploy the script in `worker-passthrough.js` (same folder). It forwards all requests to the
origin and uses `passThroughOnException()` so a bug cannot take the site down.

```bash
npm create cloudflare@latest -- api-passthrough
# copy worker-passthrough.js → src/index.js
npx wrangler deploy
# Add route: ai.welllabs.org/*
```

### Option C — Bypass Worker for API paths only

In **Workers Routes**, ensure API paths are **not** covered by the broken Worker, e.g.:

- Worker route: `ai.welllabs.org/wst/*` but **exclude** `/wst/api/*` if your plan supports it, or
- Use a **Configuration Rule** / **Page Rule** to skip Workers for URL path `/wst/api/*`

(Exact UI varies by Cloudflare plan; Option A is simplest.)

## Verify after fix

```bash
# Should return JSON (401 Unauthorized), NOT "error code: 1101"
curl -s -X POST "https://ai.welllabs.org/wst/backend/accounts/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=wrong"
```

Expected: `{"detail":"LOGIN_BAD_CREDENTIALS"}` or similar JSON — **not** a Cloudflare HTML error page.

## Google OAuth redirect URI

Ensure this URI is registered in Google Cloud Console:

```
https://ai.welllabs.org/wst/backend/accounts/auth/google/callback
```

## Debugging

- Ray ID from the error page (e.g. `a2f08a753e69ff89`) → Cloudflare dashboard → **Analytics & Logs**
- Stream Worker logs: `wrangler tail` (if you have the Worker name)
