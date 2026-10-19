from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, settings

app = FastAPI(title="TasteRoom", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "qloo": "live" if settings.qloo_live else "mock",
        "llm": "live" if settings.llm_live else "mock",
    }


# Serve the built React app from the same service (one URL, no CORS).
DIST = REPO_ROOT / "frontend" / "dist"

if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": "not found"}, status_code=404)
        candidate = (DIST / path).resolve()
        if path and candidate.is_file() and DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
