from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.outline_refine import (
    OutlinePreset,
    OutlineRefineRequest,
    OutlineRefineResponse,
    SavePresetRequest,
)
from services.database import get_async_session
from services.outline_refinement import preset_store
from services.outline_refinement.service import OutlineRefinementService

OUTLINE_REFINE_ROUTER = APIRouter(prefix="/outline-refine", tags=["Outline Refine"])


@OUTLINE_REFINE_ROUTER.post("/message", response_model=OutlineRefineResponse)
async def refine_outline_message(
    payload: OutlineRefineRequest,
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Extract or refine the slide outline for a presentation whose attached
    source file is an InDesign JSON export. The first call (no draft yet)
    extracts; later calls apply the user's edit instruction. An optional
    preset_id applies saved, content-agnostic formatting rules.
    """
    preset_rules = None
    if payload.preset_id:
        preset = await preset_store.get_preset(sql_session, payload.preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="Preset not found")
        preset_rules = preset.get("rules")

    service = OutlineRefinementService(
        sql_session,
        payload.presentation_id,
        payload.conversation_id,
    )
    result = await service.refine(payload.instruction, preset_rules=preset_rules)
    return OutlineRefineResponse(
        conversation_id=result.conversation_id,
        outlines=result.outline.slides,
        summary=result.summary,
    )


@OUTLINE_REFINE_ROUTER.get("/presets", response_model=List[OutlinePreset])
async def list_outline_presets(
    sql_session: AsyncSession = Depends(get_async_session),
):
    return await preset_store.list_presets(sql_session)


@OUTLINE_REFINE_ROUTER.post("/presets", response_model=OutlinePreset)
async def save_outline_preset(
    payload: SavePresetRequest,
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Save a reusable preset. If `rules` is omitted, they are auto-summarized
    from the presentation's refinement conversation."""
    rules = payload.rules
    if not rules:
        service = OutlineRefinementService(
            sql_session,
            payload.presentation_id,
            payload.conversation_id,
        )
        rules = await service.summarize_to_preset_rules()

    return await preset_store.save_preset(
        sql_session, name=payload.name, rules=rules
    )


@OUTLINE_REFINE_ROUTER.delete("/presets/{preset_id}")
async def delete_outline_preset(
    preset_id: str,
    sql_session: AsyncSession = Depends(get_async_session),
):
    deleted = await preset_store.delete_preset(sql_session, preset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"ok": True}
