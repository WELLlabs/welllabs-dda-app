# Authentication

Accounts use **FastAPI Users** with an HttpOnly JWT cookie (`dda_session`). Email/password
sign-up requires verification before login; Google OAuth creates verified users.

## Local entrypoint

Use the Vite app only:

- Primary: [http://localhost:5173](http://localhost:5173)
- Fallback if 5173 is busy: [http://localhost:5174](http://localhost:5174)

Do **not** open the API on `:8080` in the browser. `/api/*` is proxied by SvelteKit to FastAPI.
CORS allows both Vite ports (and `127.0.0.1` equivalents).

## Sign-up / sign-in

| Method | Flow |
|--------|------|
| Email + password | Register → Brevo verification email → verify link → login (form sets cookie) |
| Google | Authorize → callback via Vite origin → cookie → new users confirm name at `/complete-profile` |

Unverified email users cannot obtain a session (`LOGIN_USER_NOT_VERIFIED`). Authenticated APIs
require an active **and verified** user.

## Environment

Set these in `backend/.env` (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `AUTH_JWT_SECRET` | JWT signing secret (≥32 characters recommended) |
| `FRONTEND_ORIGIN` | Primary CORS / email-link origin (`http://localhost:5173`) |
| `SESSION_COOKIE_SECURE` | `true` behind HTTPS in production |
| `BREVO_API_KEY` / `BREVO_SENDER_EMAIL` / `BREVO_SENDER_NAME` | Transactional email (verify / reset / welcome) |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Optional Google button |

### Brevo

- Sender must be a **verified** Brevo sender on a domain with SPF/DKIM.
- Prefer `noreply@welllabs.org` (or similar). Sending as `*@ifmr.ac.in` through Brevo often
  soft-bounces under IFMR DMARC.
- If API calls return `401` unrecognized IP, allowlist your egress IP or disable IP blocking in
  [Brevo → Authorized IPs](https://app.brevo.com/security/authorised_ips).

### Google Cloud Console

Add **Authorized redirect URIs** (exact match):

- `http://localhost:5173/api/accounts/auth/google/callback`
- `http://localhost:5174/api/accounts/auth/google/callback`

(Plus your production HTTPS callback when deployed.)

## Schema notes

- `users` — FastAPI Users fields (`email`, `hashed_password`, `is_active`, `is_superuser`,
  `is_verified`) plus `name`
- `oauth_account` — Google (and future) OAuth linkage
- `user_qfield_credentials` — QField tokens (not on `users`)
- Opaque `sessions` table removed; auth is cookie JWT

Clean-slate local reset (destroys users and cascaded project rows):

```bash
docker compose exec -T postgis psql -U geofield -d dda_product \
  -c "TRUNCATE TABLE users CASCADE;"
```

## Related UI routes

| Path | Purpose |
|------|---------|
| `/register` | Email sign-up + Google |
| `/login` | Email login + Google + resend verification |
| `/verify` | Consume email verification token |
| `/forgot-password` / `/reset-password` | Password reset |
| `/complete-profile` | Confirm display name after first Google sign-up |

See [api.md](api.md) for endpoint details and [database.md](database.md) for tables.
