import asyncio
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from llmai import get_client
from llmai.shared import JSONSchemaResponse
from sqlalchemy.ext.asyncio import AsyncSession

from models.presentation_outline_model import PresentationOutlineModel
from models.sql.presentation import PresentationModel
from services.chat.conversation_store import ChatConversationStore
from services.outline_refinement.prompts import (
    DEFAULT_EXTRACT_INSTRUCTION,
    build_messages,
    build_preset_summary_messages,
)
from services.outline_refinement.source_preprocess import preprocess_source_json
from services.temp_file_service import TEMP_FILE_SERVICE
from utils.llm_client_error_handler import handle_llm_client_exceptions
from utils.llm_config import get_llm_config
from utils.llm_provider import get_model
from utils.llm_utils import (
    extract_text,
    generate_structured_with_schema_retries,
    get_generate_kwargs,
)
from utils.schema_utils import prepare_schema_for_validation


@dataclass
class RefineResult:
    conversation_id: uuid.UUID
    outline: PresentationOutlineModel
    summary: str


class OutlineRefinementService:
    """Chat-style extraction/refinement of slide outlines from an uploaded
    InDesign JSON export. Reuses the chat conversation store for cumulative
    history and the shared structured-output helper for schema-validated
    outline generation. The working draft is persisted on
    ``presentation.outlines`` between turns; on confirm the frontend feeds the
    outline straight into the existing ``/presentation/prepare`` endpoint.
    """

    def __init__(
        self,
        sql_session: AsyncSession,
        presentation_id: uuid.UUID,
        conversation_id: Optional[uuid.UUID] = None,
    ):
        self._sql_session = sql_session
        self._presentation_id = presentation_id
        self._conversation_id = conversation_id
        self._store = ChatConversationStore(sql_session)

    async def refine(
        self,
        instruction: Optional[str],
        *,
        preset_rules: Optional[str] = None,
    ) -> RefineResult:
        presentation = await self._sql_session.get(
            PresentationModel, self._presentation_id
        )
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")

        raw_json = self._read_source_json(presentation)
        # Compact the export (e.g. semantic-blocks) to a text-only structural
        # view so the whole document fits in context instead of being truncated.
        source_text = preprocess_source_json(raw_json)

        current_outline = presentation.get_presentation_outline()
        is_first_turn = not (current_outline and current_outline.slides)

        effective_instruction = (instruction or "").strip()
        if not effective_instruction:
            if is_first_turn:
                effective_instruction = DEFAULT_EXTRACT_INSTRUCTION
            else:
                raise HTTPException(
                    status_code=400,
                    detail="An instruction is required to refine the outline.",
                )

        conversation_id = await self._store.ensure_conversation_id(
            self._conversation_id
        )
        history = await self._store.load_history(
            presentation_id=self._presentation_id,
            conversation_id=conversation_id,
        )

        messages = build_messages(
            raw_json=source_text,
            current_outline=current_outline,
            history=history,
            instruction=effective_instruction,
            language=presentation.language,
            preset_rules=preset_rules,
        )

        # Base (unbounded count) model: split/merge edits change the slide count,
        # which a fixed-count schema would fight. /prepare tolerates any count.
        outline_schema = prepare_schema_for_validation(
            PresentationOutlineModel.model_json_schema(),
            strict=True,
        )
        response_format = JSONSchemaResponse(
            name="response",
            json_schema=outline_schema,
            strict=True,
        )

        client = get_client(config=get_llm_config())
        model = get_model()

        try:
            content = await generate_structured_with_schema_retries(
                client,
                model,
                messages=messages,
                response_format=response_format,
                json_schema=outline_schema,
                strict=True,
                validate_schema=True,
            )
        except Exception as e:
            raise handle_llm_client_exceptions(e)

        outline = PresentationOutlineModel(**content)
        if not outline.slides:
            raise HTTPException(
                status_code=502,
                detail="The model returned an empty outline. Try again.",
            )

        summary = self._build_summary(
            is_first_turn=is_first_turn,
            before=len(current_outline.slides) if current_outline else 0,
            after=len(outline.slides),
        )

        # Persist the draft so the next turn (and a page refresh) sees it.
        self._sql_session.add(presentation)
        presentation.outlines = outline.model_dump(mode="json")
        if not presentation.title and outline.slides:
            presentation.title = _derive_title(outline.slides[0].content)

        # Store the instruction + a short summary (append_turn only flushes, so
        # commit once here to persist both the draft and the chat turn).
        await self._store.append_turn(
            presentation_id=self._presentation_id,
            conversation_id=conversation_id,
            user_message=effective_instruction,
            assistant_message=summary,
        )
        await self._sql_session.commit()

        return RefineResult(
            conversation_id=conversation_id,
            outline=outline,
            summary=summary,
        )

    async def summarize_to_preset_rules(self) -> str:
        """Distill the refinement conversation into reusable, content-agnostic
        formatting rules that can be saved as a preset and applied to other
        documents."""
        conversation_id = await self._store.ensure_conversation_id(
            self._conversation_id
        )
        history = await self._store.load_history(
            presentation_id=self._presentation_id,
            conversation_id=conversation_id,
        )
        messages = build_preset_summary_messages(history)

        client = get_client(config=get_llm_config())
        model = get_model()
        try:
            response = await asyncio.to_thread(
                client.generate,
                **get_generate_kwargs(model=model, messages=messages),
            )
        except Exception as e:
            raise handle_llm_client_exceptions(e)

        rules = (extract_text(response.content) or "").strip()
        if not rules:
            raise HTTPException(
                status_code=502,
                detail="Could not summarize rules from the conversation.",
            )
        return rules

    def _read_source_json(self, presentation: PresentationModel) -> str:
        paths = TEMP_FILE_SERVICE.resolve_existing_temp_paths(
            presentation.file_paths
        )
        json_path = next(
            (p for p in paths if p.lower().endswith(".json")),
            paths[0] if paths else None,
        )
        if not json_path or not os.path.exists(json_path):
            raise HTTPException(
                status_code=400,
                detail="No InDesign JSON source file is attached to this presentation.",
            )
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read source file: {exc}",
            ) from exc

    @staticmethod
    def _build_summary(*, is_first_turn: bool, before: int, after: int) -> str:
        if is_first_turn:
            return f"Extracted an outline with {after} slide(s) from the document."
        if after > before:
            return f"Updated the outline. Slide count {before} → {after}."
        if after < before:
            return f"Updated the outline. Slide count {before} → {after}."
        return f"Updated the outline ({after} slide(s))."


def _derive_title(first_slide_content: str) -> Optional[str]:
    for line in (first_slide_content or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None
