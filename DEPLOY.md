# Deploying TasteRoom (Railway or Render, one Docker service)

**Live deployment: Railway** (see [Railway](#railway-what-we-actually-deployed) below). Render is also supported
via `render.yaml` and is documented after it.

TasteRoom is **one service**: FastAPI serves the API (`/api/*`) and the built React app on the same URL, so
there is nothing else to host. These steps take about 20 minutes. You need a GitHub account and a Render account.

> **Security first.** Your keys live only in `.env` (local) and in Render's environment settings. They are never
> committed. `./scripts/check_secrets.sh` proves it before every push.

---

## 0. Before you push anything

```bash
cd Qloo_project
./scripts/check_secrets.sh      # must print "OK: checked 2 secret value(s) ..."
git status                      # .env must NOT appear anywhere in the list
```

If the script prints `FAIL`, stop and tell Claude Code; do not push.

## Railway (what we actually deployed)

`railway.toml` tells Railway to build the repo's `Dockerfile` and health-check `/api/health`.

**Dashboard route (no CLI needed):**
1. <https://railway.com> → **New Project** → **Deploy from GitHub repo** → `tasteroom`. Railway builds the Dockerfile.
2. Open the service → **Variables** → add `QLOO_API_KEY` and `OPENAI_API_KEY` (copied from your `.env`), plus optional
   `OPENAI_MODEL_FAST=gpt-6-luna`, `OPENAI_MODEL_SMART=gpt-6.1-sol`, `RATE_LIMIT_PLAN=5/hour`, `APP_ENV=production`. Optional: `RATE_LIMIT_DISCORD` (default `10/hour`), `RATE_LIMIT_SUGGEST`, `RATE_LIMIT_ROOMS`, `RATE_LIMIT_JOIN`.
   Railway injects `PORT` itself; the container listens on it.
3. **Settings → Networking → Generate Domain** → that is your public URL.
4. Pushes to `main` redeploy automatically.

**CLI route (what was used here).** `railway login` needs an interactive terminal. In a non-interactive session, create an
account/workspace token at <https://railway.com/account/tokens>, put it in `.env` as `RAILWAY_API_TOKEN=...`, then use the
Railway GraphQL API to create the project/service/variables and `railway up -p <project> -e <env> -s <service> --ci` to
upload and deploy. `railway up` skips git-ignored files, so `.env` is never uploaded. **Revoke the token afterwards.**

**Client IPs and the rate limit.** Railway sets `X-Real-IP` to the visitor's address; the app keys its per-visitor limit
on it (falling back to the last `X-Forwarded-For` entry). This was tested live: forging both headers does not evade the limit.

**Keep it awake.** Railway services stay running by default (no sleep). Do not enable "Serverless" in the service settings.

---

## Persistent storage for invite rooms (important)

Invite rooms (`/join/<slug>`, `/room/<slug>`) **and saved plans with their undo snapshots** (`/plan/<id>`) are stored in a SQLite file at `$DATA_DIR/tasteroom.sqlite3`
(`DATA_DIR` defaults to `/data` in the Docker image). **Without a volume mounted there, rooms, saved plans and undo snapshots are lost on every
redeploy.** (Plans are pruned after 30 days.) Everything else in the app keeps working without one, and the three example communities never need it.

| Host | How |
|---|---|
| **Railway** | Service -> **Volumes** (or right-click the service on the canvas) -> **New Volume** -> mount path **`/data`**. Add the variable `DATA_DIR=/data`. Redeploy. (Via API: the `volumeCreate` mutation with `projectId`, `environmentId`, `serviceId` and `mountPath: "/data"`.) |
| **Render** | A persistent **Disk** (paid instance types): `render.yaml` already declares one at `/data`. |
| **Docker** | `docker run -v tasteroom-data:/data ...` |

A mounted volume arrives owned by root, but the app runs as an unprivileged user (uid 10001). The image's entrypoint
(`docker-entrypoint.sh`) starts as root only to `chown` the data directory and then drops privileges with `setpriv`, so
**no `RAILWAY_RUN_UID=0` workaround is needed**. This was tested with a root-owned volume: the process runs as uid 10001,
writes succeed, and a room survives a container restart and a brand-new container on the same volume.

Notes: the file is a single SQLite database (one app instance, WAL mode); back it up by copying `tasteroom.sqlite3`.
The organizer token of each room is stored only as a SHA-256 hash. The **demo room** (`/room/demo?t=demo-room`) is re-seeded at
every start and visitor responses in it are cleared after 12 hours.

## 1. Put the code on GitHub (public repo, required by the hackathon)

*(Done: <https://github.com/shedybaba/tasteroom>.)*

1. Go to <https://github.com/new>.
2. **Repository name:** `tasteroom` (any name works). **Public.** Do **not** tick "Add a README", "Add .gitignore"
   or "Choose a license" (the repo already has them).
3. Click **Create repository**. Copy the repo URL shown (it ends in `.git`).
4. In the terminal:
   ```bash
   cd Qloo_project
   git remote add origin https://github.com/<your-username>/tasteroom.git
   git push -u origin main
   ```
   (Or, if you have the GitHub CLI logged in: `gh repo create tasteroom --public --source=. --push`.)
5. On the repo page, click the **gear icon next to "About"** (top right) and:
   - **Description:** `AI agent that turns a community's tastes into an event brief, powered by Qloo taste data`
   - **Website:** your Render URL (fill in after step 2)
   - Tick nothing else needed; GitHub reads `LICENSE` automatically and shows **MIT license** in the About box.
   - **Topics:** `qloo`, `ai-agent`, `fastapi`, `react`, `hackathon`
6. Reload the page and confirm the sidebar shows "MIT license".

## 2. Render alternative: create the Render service

1. Sign up / log in at <https://render.com> (you can sign in with GitHub).
2. Click **New +** (top right) → **Blueprint**.
3. **Connect** your GitHub account if asked, then pick the `tasteroom` repo. Render reads `render.yaml`.
4. It asks for the two secret values. Paste them into the boxes (this is the only place besides `.env`):
   - `QLOO_API_KEY` = your Qloo hackathon key
   - `OPENAI_API_KEY` = your OpenAI key
5. **Choose the plan:**
   - **Starter (~$7/month): recommended.** Always on, no cold starts while judges look. It is what `render.yaml` selects.
   - **Free:** sleeps after ~15 minutes idle (first visit then takes ~30-60 s to wake). If you choose Free, edit
     `plan: starter` to `plan: free` in `render.yaml`, commit, push, **and** set up the keep-alive in step 4.
6. Click **Apply** / **Create**. The first build takes about 3-5 minutes (Docker build: React, then Python).
7. When the dashboard shows **Live**, click the URL at the top (`https://tasteroom-xxxx.onrender.com`).

## 3. Check the live site

Open each of these on your Render URL:

| Check | Expect |
|---|---|
| `/api/health` | `{"ok":true,"qloo":"live","llm":"live"}` (if it says `mock`, a key is missing: go to **Environment** in Render, add it, and **Manual Deploy → Deploy latest commit**) |
| `/` | Landing page with 3 example cards |
| Click each example | Results open instantly; the Compare tab shows the LLM-vs-Qloo stats |
| `/build` → paste a list → **Check tastes** → **Build event plan** | A plan in about 40-60 s, mode badge says "AI agent" |

If the build plan says "Live planning is limited to 5/hour", that is the cost-control rate limit working (per visitor).
Change it with the `RATE_LIMIT_PLAN` environment variable in Render (for example `20/hour`) and redeploy.

## 4. Keep it awake (Free plan only)

Skip this on Starter.

1. Create a free account at <https://uptimerobot.com>.
2. **Add New Monitor** → type **HTTP(s)**, URL `https://<your-service>.onrender.com/api/health`, interval **5 minutes**.
3. Save. Leave it running until judging ends (Oct 30, 2026, 11:45pm EDT is the submission deadline; judging follows).

## 5. Updating the site

Any `git push` to `main` redeploys automatically (`autoDeploy: true`). To redeploy without a code change:
Render dashboard → your service → **Manual Deploy** → **Deploy latest commit**.

## 6. Spending safety

- Set a **monthly spending limit** on your OpenAI account (platform.openai.com → Settings → Limits).
- Example communities are saved on disk, so judges clicking them cost nothing.
- Each live plan costs a few cents of OpenAI usage. `RATE_LIMIT_PLAN` caps this per visitor.

## 7. Optional: custom domain

Render dashboard → your service → **Settings** → **Custom Domains** → **Add**. Follow the DNS instructions it shows.

## Run the same image locally

```bash
docker build -t tasteroom .
docker run --rm -p 8000:8000 \
  -e QLOO_API_KEY=... -e OPENAI_API_KEY=... tasteroom
# open http://localhost:8000
```
With no keys it still runs end to end in mock mode (saved samples, templated brief).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails at `npm ci` | The frontend `package-lock.json` must be committed (it is). Re-run the deploy. |
| `/api/health` shows `"qloo":"mock"` | `QLOO_API_KEY` is missing or empty in Render → Environment. |
| Plans show "The AI agent hit a problem" | OpenAI key invalid/expired or out of credit; the app still works via the fallback pipeline. Fix the key in Render → Environment. |
| Plans say "Qloo taste service is unavailable" | Qloo rate limit or outage; wait a minute. Responses are cached for 24 h. |
| Site is slow on first visit | Free plan waking up; use Starter or the step-4 keep-alive. |
