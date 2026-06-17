"""Preprocess an uploaded InDesign/HWPX JSON export into a compact, text-only
view before handing it to the LLM.

The "semantic-blocks" export (version "sbd-*") is dominated by non-text
metadata (coordinates, bboxes, member ids, confidence signals) that waste
context tokens. For that format we keep only the reading-ordered structural
labels and page numbers, which preserves the document's logical outline while
shrinking it ~98%. Any other JSON is returned as-is (pretty-printed) so the
feature stays tolerant of unknown shapes.
"""

import json
from typing import Any

# Paragraph-style placeholders that carry no semantic meaning.
_NOISE_DISPLAY_NAMES = {
    "$ID/[No paragraph style]",
    "$ID/NormalParagraphStyle",
}


def _is_semantic_blocks(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("version"), str)
        and data["version"].startswith("sbd")
        and isinstance(data.get("blocks"), list)
    )


def _collect_text(value: Any, out: list[str]) -> None:
    """Recursively pull any human-readable string values out of a block's
    members/text fields, if the export happens to embed real text."""
    if isinstance(value, str):
        s = value.strip()
        if s:
            out.append(s)
    elif isinstance(value, list):
        for item in value:
            _collect_text(item, out)
    elif isinstance(value, dict):
        for key in ("text", "content", "value", "runs", "members", "texts"):
            if key in value:
                _collect_text(value[key], out)


def _render_semantic_blocks(data: dict) -> str:
    blocks = data.get("blocks", [])
    summary = data.get("summary", {})
    source = data.get("source", {})

    lines: list[str] = []
    doc_name = source.get("document_name")
    if doc_name:
        lines.append(f"Document: {doc_name}")
    if summary:
        lines.append(
            "Summary: "
            f"{summary.get('pages', '?')} pages, "
            f"{summary.get('blocks', '?')} blocks"
        )
    lines.append("")
    lines.append("Document structure (reading order, one block per line):")

    ordered = sorted(
        blocks, key=lambda b: b.get("reading_order", 0) if isinstance(b, dict) else 0
    )
    for blk in ordered:
        if not isinstance(blk, dict):
            continue
        label = (blk.get("display_name") or "").strip()
        if not label or label in _NOISE_DISPLAY_NAMES:
            continue
        page = blk.get("page_start")
        prefix = f"p{page}: " if page is not None else ""
        # If real text is embedded anywhere in the block, append a snippet.
        texts: list[str] = []
        _collect_text(blk.get("debug"), texts)
        _collect_text(blk.get("members"), texts)
        snippet = " ".join(t for t in texts if not t.isdigit())[:200]
        if snippet:
            lines.append(f"{prefix}{label} — {snippet}")
        else:
            lines.append(f"{prefix}{label}")

    return "\n".join(lines)


def preprocess_source_json(raw_json: str) -> str:
    """Return a compact text view of the source for the LLM. Falls back to the
    original string if it is not the semantic-blocks format or cannot be parsed.
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError):
        return raw_json

    if _is_semantic_blocks(data):
        rendered = _render_semantic_blocks(data)
        # Guard against a degenerate render (no labels survived).
        if rendered.strip():
            return rendered

    return raw_json
