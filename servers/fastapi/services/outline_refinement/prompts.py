from typing import List, Optional

from llmai.shared import AssistantMessage, Message, SystemMessage, UserMessage

from models.presentation_outline_model import PresentationOutlineModel

# Default instruction used for the very first turn, when there is no existing
# draft and the user has not typed anything yet.
DEFAULT_EXTRACT_INSTRUCTION = (
    "Extract a clean, presentation-ready slide outline from this InDesign document."
)

# Hard cap on the raw InDesign JSON injected into the prompt to avoid blowing the
# model context window on large exports. Truncation is marked explicitly.
MAX_SOURCE_CHARS = 60000


def _truncate_source(raw_json: str) -> str:
    if len(raw_json) <= MAX_SOURCE_CHARS:
        return raw_json
    head = raw_json[:MAX_SOURCE_CHARS]
    return f"{head}\n... [truncated {len(raw_json) - MAX_SOURCE_CHARS} chars]"


def get_system_prompt() -> str:
    return (
        "You convert an InDesign export (raw JSON) into a list of presentation "
        "slide outlines, and then apply the user's editing instructions, "
        "re-emitting the FULL outline every time.\n"
        "Treat the InDesign JSON as loosely-structured source content: extract "
        "headings, body text, and ordering. Do NOT assume a fixed schema and do "
        "NOT echo raw JSON keys.\n"
        "Each slide's `content` must be a self-contained Markdown string:\n"
        "   - Must start with a ## title.\n"
        "   - Must be in Markdown format.\n"
        "   - Don't use **bold** or __italic__ text.\n"
        "   - Around 40 words, detailed enough to generate a good slide.\n"
        "   - The first slide title must be the presentation title.\n"
        "Give each slide one clear purpose and split overloaded topics across "
        "multiple slides. Build a coherent narrative from start to finish.\n"
        "Apply the user's editing instruction literally to the exact slide(s) "
        "mentioned. When asked to split a slide, increase the slide count; when "
        "asked to merge, decrease it.\n"
        "ALWAYS return ALL slides, renumbered from the start. NEVER return a diff "
        "or only the changed slides.\n"
        "Do not include URLs, hyperlinks, citations, footnotes, or branding/"
        "styling information in the outline.\n"
        "Use only information present in the provided source document."
    )


def build_messages(
    *,
    raw_json: str,
    current_outline: Optional[PresentationOutlineModel],
    history: List[dict],
    instruction: str,
    language: Optional[str] = None,
    preset_rules: Optional[str] = None,
) -> List[Message]:
    messages: List[Message] = [SystemMessage(content=get_system_prompt())]

    # Reusable, content-agnostic rules from a saved preset are applied to every
    # extraction so a different document gets the same structure/style.
    if preset_rules and preset_rules.strip():
        messages.append(
            SystemMessage(
                content=(
                    "Apply these reusable formatting rules to the outline "
                    "(they describe structure/style, not this document's "
                    "content):\n" + preset_rules.strip()
                )
            )
        )

    source_block = (
        "InDesign source document:\n```json\n"
        f"{_truncate_source(raw_json)}\n```"
    )
    if language:
        source_block += f"\n\nWrite all slide content in this language: {language}."
    messages.append(UserMessage(content=source_block))

    if current_outline and current_outline.slides:
        messages.append(
            UserMessage(
                content="Current outline draft:\n" + current_outline.to_string()
            )
        )

    # Replay prior turns so instructions are cumulative. History rows are
    # {"role": "user"|"assistant", "content": str}.
    for turn in history:
        role = turn.get("role")
        content = turn.get("content") or ""
        if not content:
            continue
        if role == "assistant":
            # AssistantMessage expects a list content (mirrors chat service).
            messages.append(AssistantMessage(content=[content]))
        elif role == "user":
            messages.append(UserMessage(content=content))

    messages.append(UserMessage(content=instruction))
    return messages


def build_preset_summary_messages(history: List[dict]) -> List[Message]:
    """Distill a refinement conversation into reusable, content-agnostic rules."""
    system = (
        "You extract REUSABLE outline-formatting rules from a refinement chat. "
        "The user has been editing a slide outline derived from one document. "
        "Summarize their instructions as a short list of general rules that "
        "could be applied to a DIFFERENT document of the same kind.\n"
        "Keep only structure/style/formatting rules (slide count targets, how "
        "to group or split sections, ordering, length/tone). "
        "DROP anything specific to this document's subject matter.\n"
        "Return a concise plain-text list, one rule per line. No preamble."
    )
    transcript_lines = []
    for turn in history:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            transcript_lines.append(f"User: {content}")
        elif role == "assistant":
            transcript_lines.append(f"Assistant: {content}")
    transcript = "\n".join(transcript_lines) or "(no instructions yet)"

    return [
        SystemMessage(content=system),
        UserMessage(content="Refinement conversation:\n" + transcript),
    ]
