# DocuFlow AP – frontend

Vite + React + Tailwind. Windows-7 style on purpose (Tahoma 12px, `.panel`,
`.btn`, `.input-retro`); keep new screens in the same family.

## Screens
- **Sign in** – people have their own accounts (D-118). A new account starts
  with a temporary password and must choose its own at first sign-in.
- **Dashboard** – case KPIs, recent cases, top exception codes for the selected customer.
- **Upload & Match** – drop files or choose a folder; one sub-folder (or one
  number in the file names) is one case. PNG, JPG or PDF (up to 4 pages).
- **Review Queue** – cases waiting for a person, oldest first.
- **Case Review** – the scan next to the extracted values. Correct a misread
  value and press *Save & Re-check*, or approve / reject with a note. Every
  step is a new audit row with the person's username; nothing is overwritten.
- **Audit Trail** – every run, with the full decision record.
- **Users** (admins only) – add people, reset passwords, switch accounts off.

## On the server
`docker-compose.server.yml` builds this folder into an nginx container on
port 8090 (`DOCUFLOW_UI_PORT` to change it). nginx serves the app and forwards
`/api/*` to the API, so the page holds no API URL and no key.
First admin (once, on the server):
```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml --env-file .env.server \
  exec api /opt/venv/bin/python -m apmatch.auth create-user <username> "<Full Name>" --admin
```
It prints a temporary password. Further accounts are added in the Users tab.

## Development
```bash
bun install
VITE_API_URL=http://<server>:8001 bun run dev    # sign in with your own account
bun run build                                    # static files in dist/ (API at /api)
```
