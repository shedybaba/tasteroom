"""Slim a heavy Qloo entity down to what the LLM and frontend need."""
from typing import Any

from .models import SlimEntity

MAX_TAG_NAMES = 8
MAX_TAG_IDS = 30


def _entity_type(raw: dict[str, Any]) -> str:
    # /search gives types=[...]; /v2/insights gives type="urn:entity" + subtype="urn:entity:place".
    if raw.get("subtype"):
        return raw["subtype"]
    types = raw.get("types") or []
    if types:
        return types[0]
    return raw.get("type") or ""


def _image(props: dict[str, Any]) -> str | None:
    img = props.get("image")
    if isinstance(img, dict) and img.get("url"):
        return img["url"]
    imgs = props.get("images")
    if isinstance(imgs, list) and imgs and isinstance(imgs[0], dict):
        return imgs[0].get("url")
    return None


def slim_entity(raw: dict[str, Any]) -> SlimEntity:
    props = raw.get("properties") or {}
    tags = raw.get("tags") or []
    # Qloo's generic audience tags ("Loyal", "Passionate") are noise in explanations: list them last.
    ordered = sorted(tags, key=lambda t: str(t.get("type", "")).startswith("urn:tag:audience"))
    tag_ids = [t.get("tag_id") or t.get("id") or t.get("value") for t in tags]

    query = raw.get("query") or {}
    explain_rows = (query.get("explainability") or {}).get("signal.interests.entities") or []
    explain = {
        str(r["entity_id"]).upper(): float(r["score"])
        for r in explain_rows
        if r.get("entity_id") and r.get("score") is not None
    }

    return SlimEntity(
        id=str(raw.get("entity_id") or raw.get("id") or "").upper(),
        name=raw.get("name") or "",
        type=_entity_type(raw),
        popularity=raw.get("popularity"),
        description=props.get("short_description") or props.get("description"),
        image=_image(props),
        address=props.get("address"),
        website=props.get("website"),
        tags=[t["name"] for t in ordered if t.get("name")][:MAX_TAG_NAMES],
        tag_ids=[i for i in tag_ids if i][:MAX_TAG_IDS],
        affinity=query.get("affinity"),
        explain=explain,
    )
