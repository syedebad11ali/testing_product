# Security policy

## Reporting a vulnerability
Email the project owner privately (do not open a public issue). Include steps to reproduce and the affected path. <!-- OWNER: add the real security contact address here. -->

## What is in place (see docs/AUTH.md, docs/COOKIES.md, docs/MESSAGING.md)
Server sessions in `__Host-` cookies, CSRF (Origin check + double submit) on write routes, per-IP/per-user rate limits, audit log, ban/suspend moderation, strict CSP `style-src` on every page except `/chatbot-demo`, private messaging with identical 404s for non-participants and no message bodies in logs, and no message content sent to AI providers.

## Known gaps (honest list)
Admin TOTP/step-up is built but enforcement is optional and untested against a real authenticator app; recovery is an operator script; PostgreSQL adapter never run against a real database; dependency pins and vulnerability scans not run; `/chatbot-demo` CSP permissive; Tesseract/PDF.js/fonts not self-hosted. Details: `docs/KNOWN_ISSUES.md`.

## Dev-only shortcut
`/login` links to a separate **Developer Login** page (`/developer-login`; admins only, everything else goes to `/nice-try`). The local-development `admin__01` shortcut (`/auth/dev-skip`, also accepted by that page) is disabled in production, needs `DEV_ADMIN_PASSWORD` (empty by default) to open `/admin`, and refuses to run against a `DATABASE_URL`. Never set `DEV_ADMIN_PASSWORD` on Vercel.

## Secrets
Never commit `.env`. Gemini/OpenAI keys that were exposed earlier must be treated as compromised and rotated before any live AI use.
