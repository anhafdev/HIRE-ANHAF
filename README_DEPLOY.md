# Deploy: bot + admin website (Coolify, 1 click)

One compose stack runs both services. They share a `data` volume
(SQLite lives there), and the bot pushes live events to the website
over the internal `http://web:3000` address.

## Coolify setup (VPS)

1. Push this repo to GitHub (private repo is fine).
2. Coolify → New Project → Docker Compose → connect the repo.
3. Compose file: `docker-compose.yml` (repo root).
4. Environment variables — set these in the Coolify UI
   (copy the rest from `.env.example` as needed):

   | Key | Value |
   |---|---|
   | `BOT_TOKEN` | telegram bot token |
   | `ADMIN_ID` | your telegram id |
   | `ADMIN_USER` | website login name |
   | `ADMIN_PASS` | website login password |
   | `JWT_SECRET` | long random string |
   | `ADMIN_WEB_TOKEN` | another random string |
   | `CV_ADDR_*` | your wallet addresses |

   Generate secrets, e.g. `python -c "import secrets; print(secrets.token_hex(32))"`.

5. Attach a domain to the **web** service, port **3000**. Coolify gives HTTPS.
6. Deploy. Both `bot` and `web` start together.

Open `https://your-domain/` → login → live dashboard.
The websocket (`/ws`) runs on the same domain, no extra config.

## Local run (same stack)

```bash
cp .env.example .env
# fill BOT_TOKEN, ADMIN_PASS, JWT_SECRET, ADMIN_WEB_TOKEN, CV_ADDR_*
docker compose up --build
```

- Website: http://127.0.0.1:3000
- Bot polls Telegram from the `bot` container.

## Notes

- First deploy starts a fresh database inside the `data` volume.
  To migrate history, copy `hire_bot.db` into the volume once.
- `ADMIN_WEB_URL` is set by compose already (`http://web:3000`).
  Only override it for non-docker local runs.
