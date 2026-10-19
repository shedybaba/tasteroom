import json
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture
def sample():
    def load(name: str):
        return json.loads((SAMPLES / f"{name}.json").read_text())
    return load
