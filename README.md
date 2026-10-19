# TasteRoom

**Stop guessing what your community wants. Plan events from real taste data.**

TasteRoom is an AI agent for community organizers (Discord, meetups, clubs, brand communities). Enter what
3 to 15 members like and the city; the agent resolves those tastes to [Qloo](https://qloo.com) entities, builds one
community taste profile, queries Qloo for **music, venues, sponsors and content**, and writes an **event brief** where
every pick comes from Qloo and is explained. A **Compare** tab shows the same request answered by a plain LLM.

**Live demo:** https://tasteroom-production-d52a.up.railway.app

Built for the Qloo Agentic Hackathon. Full README (architecture, endpoint table, screenshots) is being finalised;
see `BUILD_PLAN.md`, `API_FINDINGS.md` (what the live Qloo API actually does) and `DEPLOY.md`.

## Run locally

```bash
cp .env.example .env     # add your keys; .env is git-ignored. With no keys the app runs in mock mode.
make setup
make dev-api             # terminal 1: FastAPI on :8000
make dev-web             # terminal 2: Vite on :5173 (proxies /api to :8000)
```

Production-style (one port): `make serve`, then open http://localhost:8000. Tests: `make test` (backend) and
`cd frontend && npm test`.

## Docker / deploy

```bash
docker build -t tasteroom . && docker run --rm -p 8000:8000 -e QLOO_API_KEY=... -e OPENAI_API_KEY=... tasteroom
```
Step-by-step Railway (or Render) deployment: [`DEPLOY.md`](DEPLOY.md). Before any push run `./scripts/check_secrets.sh`.

## License

[MIT](LICENSE)
