# Running Open Notebook

A practical guide to running this app locally or on a server.

> This fork adds **per-browser chat session isolation** (each visitor sees only
> their own conversations, which are ephemeral) while notebooks and sources stay
> shared. See [Multi-user chat isolation](#multi-user-chat-isolation) below.
>
> ⚠️ **Important:** the committed `docker-compose.yml` pulls the *published upstream*
> image, which does **not** include this fork's changes. To run this fork's code you
> must **build from source** (see Option A).

---

## Architecture & ports

The app has three parts. The Docker image bundles the frontend + API together
(run by supervisord) and talks to a separate SurrealDB container.

| Component | Docker port | Native dev port |
|-----------|-------------|-----------------|
| Web UI (what users open) | **8502** | 3000 |
| REST API | **5055** | 5055 |
| SurrealDB (database) | 8000 | 8000 |

---

## Prerequisites

- **Docker path (recommended):** Docker + Docker Compose (Docker Desktop on Win/Mac).
- **Native dev path:** Python 3.11+ with [`uv`](https://docs.astral.sh/uv/), Node.js 20+, and Docker (for SurrealDB only).

---

## 1. Configure

Create your environment file from the template and set a secret encryption key
(this encrypts AI provider keys stored in the database):

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```dotenv
# Required — any secret string (min ~16 chars). Keep it stable; changing it
# makes previously-stored API keys undecryptable.
OPEN_NOTEBOOK_ENCRYPTION_KEY=replace-with-your-own-secret

# Optional — how long an idle chat session lives before it is purged.
# 24 = 24 hours (default). Set 0 to disable purging. Use e.g. 0.05 (~3 min) to test.
CHAT_SESSION_TTL_HOURS=24
```

AI provider keys (OpenAI, Anthropic, …) are **optional here** — the recommended
way is to add them later in the UI under **Settings → API Keys**. You only need
them configured (here or in the UI) to actually send chat messages.

> `.env` is git-ignored and is never committed — keep your real keys there.

---

## 2. Run with Docker

### Option A — Build from source (this fork, **recommended**)

Builds the image from the local code so the chat-isolation feature is included.
Create a `docker-compose.build.yml` next to `docker-compose.yml`:

```yaml
services:
  surrealdb:
    image: surrealdb/surrealdb:v2
    command: start --log info --user root --pass root rocksdb:/mydata/mydatabase.db
    user: root
    ports:
      - "8000:8000"
    volumes:
      - ./surreal_data:/mydata
    environment:
      - SURREAL_EXPERIMENTAL_GRAPHQL=true
    restart: unless-stopped

  open_notebook:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8502:8502"
      - "5055:5055"
    env_file:
      - ./.env
    environment:
      - SURREAL_URL=ws://surrealdb:8000/rpc
      - SURREAL_USER=root
      - SURREAL_PASSWORD=root
      - SURREAL_NAMESPACE=open_notebook
      - SURREAL_DATABASE=open_notebook
    volumes:
      - ./notebook_data:/app/data
    depends_on:
      - surrealdb
    restart: unless-stopped
```

Then build and start (the first build takes ~5–15 min):

```bash
docker compose -f docker-compose.build.yml up -d --build
```

After changing any source code, re-run that command **with `--build`** to rebuild.

### Option B — Published upstream image (no fork changes)

The committed `docker-compose.yml` pulls `lfnovo/open_notebook:v1-latest`. Set your
encryption key in that file (or rely on its inline value), then:

```bash
docker compose up -d
```

### View logs / stop

```bash
docker compose -f docker-compose.build.yml logs -f open_notebook   # follow logs
docker compose -f docker-compose.build.yml down                    # stop
```

A healthy startup logs `API initialization completed successfully` and
`Chat session sweeper started`.

---

## 3. Open the app

- **Web UI:** http://localhost:8502
- **API docs (Swagger):** http://localhost:5055/docs

---

## 4. Run on a server (LAN / cloud)

1. Use the server's IP or domain, not `localhost`: `http://<server-ip>:8502`.
2. Open firewall / security-group ports **8502** and **5055**.
3. If the UI loads but shows **no data**, the frontend can't reach the API. Set the
   API URL so the browser targets the right host (in the `open_notebook` service env):
   ```yaml
   environment:
     - API_URL=http://<server-ip-or-domain>:5055
   ```
4. **Production tip:** put Nginx/Caddy in front for a domain + HTTPS on port 443,
   proxying the UI and API under one origin (avoids cross-port issues).

---

## Multi-user chat isolation

This fork lets you host one shared library for several anonymous users while keeping
each person's conversations private and temporary:

- **Shared:** notebooks, sources, notes (everyone sees the same library).
- **Private:** chat sessions are scoped to a per-browser id (`X-Client-ID`, stored in
  `sessionStorage`). You only see chats you created.
- **Ephemeral:** closing the tab drops the id, so old chats disappear from the UI; a
  background sweeper deletes sessions idle past `CHAT_SESSION_TTL_HOURS` from disk.

**Quick test:** open the app in a normal window and an incognito window on the same
notebook. Each window sees only its own chat sessions, while notebooks/sources are
identical in both.

---

## Native development (no Docker for the app)

Useful for hot-reloading while developing. Frontend dev server runs on **port 3000**.

```bash
cp .env.example .env          # set OPEN_NOTEBOOK_ENCRYPTION_KEY
make database                 # start SurrealDB in Docker (port 8000)
make start-all                # API (5055) + background worker + frontend (3000)
```

Or run pieces individually:

```bash
make api            # uv run run_api.py            -> API on :5055
make worker-start   # surreal-commands worker      -> async jobs (embeddings, podcasts)
make frontend       # cd frontend && npm run dev   -> UI on :3000
```

Stop everything: `make stop-all`.

Run the test suite: `uv run pytest tests/`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| UI loads but no data / network errors | API unreachable — set `API_URL` (see server section) and check port 5055 is open |
| Fork feature missing (everyone sees all chats) | You ran the published image — use **Option A** to build from source |
| "Encryption key not set" warnings | Set `OPEN_NOTEBOOK_ENCRYPTION_KEY` in `.env` |
| Can't send chat messages | Configure an AI provider key in **Settings → API Keys** |
| Old chats never disappear on disk | `CHAT_SESSION_TTL_HOURS` is `0` (disabled) — set a positive value |
| Port already in use | Stop the conflicting service or change the host port mapping in compose |
