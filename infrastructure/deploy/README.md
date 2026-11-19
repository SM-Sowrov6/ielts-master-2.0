# Single-server deployment (free tier)

Everything runs on one Oracle Cloud Always Free VM with Docker Compose. Caddy serves HTTPS,
Cloudflare provides DNS, and R2 stores media. LiveKit Cloud and the Gemini API are external.

| File | Purpose |
|---|---|
| `compose.prod.yml` | postgres, redis, migrate (one-off), backend, worker, frontend, voice, caddy |
| `Caddyfile` | HTTPS + routing (`/api/*` → backend, rest → frontend; `/api/v1/internal/*` blocked) |
| `env.production.example` | every setting, documented; copy to `.env` on the server (never commit it) |
| `setup-server.sh` | one-time: Docker, host firewall 80/443, swap, clone |
| `deploy.sh` | build + (re)start; run after every `git pull` (migrations run automatically) |
| `backup.sh` | nightly `pg_dump` (cron), keeps 14 days; also copy dumps off the server |

## First deployment

1. **Oracle VM**: Ubuntu 24.04, Ampere A1 Flex (4 OCPU / 24 GB). In the VCN security list, add
   ingress rules for TCP 80 and 443 (and UDP 443) from `0.0.0.0/0`.
2. **DNS (Cloudflare)**: `A` records for `@` and `www` → the VM's public IP. Keep them
   **DNS only (grey cloud)** until Caddy has issued the certificate, then switch to Proxied and
   set SSL/TLS mode to **Full (strict)**.
3. **R2**: create bucket `ielts-media`; create an API token (Object Read & Write, this bucket);
   add a CORS rule allowing `GET, PUT, HEAD` from `https://<your domain>` with header
   `content-type`.
4. **Server**:
   ```bash
   scp infrastructure/deploy/setup-server.sh ubuntu@<ip>:~
   ssh ubuntu@<ip> 'bash setup-server.sh https://github.com/<owner>/<repo>.git'
   # log out/in, then:
   cd ~/ielts-master && nano infrastructure/deploy/.env   # fill every value
   bash infrastructure/deploy/deploy.sh
   ```
   A private repository needs a GitHub deploy key or a fine-grained read-only token to clone.
5. **First Super Admin** (password is prompted, never echoed):
   ```bash
   docker compose -f infrastructure/deploy/compose.prod.yml --env-file infrastructure/deploy/.env \
     exec backend python /app/admin_cli.py create-staff you@example.com --full-name "Your Name"
   ```
   Sign in at `/sign-in`, open `/admin`, and enrol the authenticator app (2FA is mandatory in
   production). Store the recovery codes safely. Lost both? `... exec backend python
   /app/admin_cli.py reset-mfa you@example.com`.
6. **Content**: publish the Writing and Speaking rubrics (four-eyes) so AI evaluation can run.
7. **Open registration** once `/terms` and `/privacy` are approved: set `LEGAL_APPROVED = true`
   in `frontend/src/components/legal/legal-page.tsx`, and in `.env` set
   `LEGAL_TERMS_VERSION` / `LEGAL_PRIVACY_VERSION` to its `LEGAL_VERSION` and
   `REGISTRATION_ENABLED=true`; then `deploy.sh`.

## Updating

```bash
cd ~/ielts-master && git pull && bash infrastructure/deploy/deploy.sh
```

Logs: `docker compose -f infrastructure/deploy/compose.prod.yml --env-file infrastructure/deploy/.env logs -f backend worker voice caddy`
