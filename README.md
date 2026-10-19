# TasteRoom

An AI agent for community organizers. Enter what your members like and the city; TasteRoom resolves
those tastes to [Qloo](https://qloo.com) entities, builds one community taste profile, and produces an
event brief (music, venues, sponsors, content) where every pick comes from Qloo and is explained.

Built for the Qloo Agentic Hackathon. Work in progress; see `BUILD_PLAN.md`.

## Run locally

```bash
cp .env.example .env     # add your keys; .env is git-ignored. With no keys the app runs in mock mode.
make setup
make dev-api             # terminal 1: FastAPI on :8000
make dev-web             # terminal 2: Vite on :5173 (proxies /api to :8000)
```

Production-style (one port): `make serve`, then open http://localhost:8000.

## License

MIT
