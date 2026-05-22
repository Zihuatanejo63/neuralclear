from __future__ import annotations

from server.registry import build_default_registry, manifest_for


def provider_manifest() -> dict[str, object]:
    registry = build_default_registry()
    return manifest_for(registry.get("agent.pdf_summarizer"))


def summarize_pdf_text(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:220] + ("..." if len(cleaned) > 220 else "")
