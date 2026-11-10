# DocuFlow AP – frontend

Vite + React + Tailwind. Windows-7 style on purpose (Tahoma 12px, `.panel`,
`.btn`, `.input-retro`); keep new screens in the same family.

## Screens
- **Dashboard** – case KPIs, recent cases, top exception codes for the selected customer.
- **Upload & Match** – drop files or choose a folder; one sub-folder (or one
  number in the file names) is one case. Images only for now.
- **Review Queue** – cases waiting for a person, oldest first.
- **Case Review** – the scan next to the extracted values. Correct a misread
  value and press *Save & Re-check*, or approve / reject with a note.
  Every step is a new audit row; nothing is overwritten (D-117).
- **Audit Trail** – every run, with the full decision record.

## Run
```bash
bun install
VITE_API_URL=http://<server>:8001 VITE_API_KEY=<key> bun run dev      # development
VITE_API_URL=http://<server>:8001 VITE_API_KEY=<key> bun run build    # static files in dist/
bun run preview --host 0.0.0.0 --port 4173                           # serve dist/
```
`VITE_API_KEY` is compiled into the browser bundle: anyone who can open the
page can read it. Serve the UI only on a private network (Tailscale) until
per-user login exists (UI-2).
