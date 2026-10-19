import json
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture
def sample():
    def load(name: str):
        return json.loads((SAMPLES / f"{name}.json").read_text())
    return load


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Never touch the real disk cache from tests."""
    from diskcache import Cache

    from app import cache
    monkeypatch.setattr(cache, "_cache", Cache(str(tmp_path / "cache")))


class OfflineClient:
    """Factory: a QlooClient that reports live mode (mock=False) but serves saved samples."""

    @staticmethod
    def make():
        from app.qloo_client import QlooClient

        class _C(QlooClient):
            async def request(self, path, params, **kw):
                return self._mock(path, params)

        return _C(api_key="x", mock=False)


@pytest.fixture
def offline_client():
    return OfflineClient.make()
