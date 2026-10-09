# Security

- **Passwords**: argon2id (argon2-cffi). Minimum 10 chars.
- **Sessions**: random 256-bit token in an `HttpOnly`, `SameSite=Lax`, `Secure` (non-dev) cookie; only its SHA-256 is stored. 12 h expiry, revocable on logout.
- **CSRF**: per-session token returned by login/me; every mutating request must send `X-CSRF-Token` (checked server-side), plus SameSite cookie.
- **Brute force / rate limiting**: Redis counters (in-memory fallback if Redis is down, logged as degraded). 10 requests/min/IP on login; account locks 15 min after 5 consecutive failures; generic error message for wrong credentials (a locked account returns a distinct 429, which reveals that the account exists). Uploads are limited to 60/min per user. There is no global per-IP API limit in Phase 1 (put one on the reverse proxy).
- **RBAC server-side** (see `ROLE_PERMISSION_MATRIX.md`) with object-level checks: employees can only read/modify their own expenses/documents/reconciliations; household scoping on every query. Cross-employee access returns 404 (not 403) to avoid existence leaks.
- **Uploads**: allowlist JPG/PNG/HEIC/PDF, magic-byte sniffing (client MIME not trusted), 15 MB max, image decoded with Pillow to confirm validity, PDF page cap, SHA-256 stored. Filenames are never used as storage paths (random keys).
- **Storage**: private bucket / private directory; access only via short-lived (5 min) signed URLs issued after an authorization check. Local backend uses HMAC-signed URLs.
- **Secrets**: only via environment variables; `.env.example` has placeholders; `.env` is git-ignored. Production refuses to start with the default `SECRET_KEY`.
- **Logging**: structured logs contain ids and event names only; no emails, names, receipt text, or amounts in logs. OCR text lives only in the DB.
- **Audit**: append-only `audit_log` (DB trigger blocks UPDATE/DELETE) for all financially significant actions: posting, reversal, approval, rejection, reconciliation close/reopen, user/role changes, document access, login lockouts.
- **Headers**: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` on web and API. No Content-Security-Policy yet (known gap).
- **Demo data** is seeded only by an explicit CLI command that refuses to run when `APP_ENV=production`; demo household is labelled `DEMO`.
- **Known gaps (Phase 1)**: no MFA, no email password reset, no virus scanning, no encryption at rest beyond what disk/MinIO provide, no formal penetration test.
