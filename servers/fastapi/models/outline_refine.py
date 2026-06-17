import uuid
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.presentation_outline_model import SlideOutlineModel


class OutlineRefineRequest(BaseModel):
    presentation_id: uuid.UUID
    # Optional: the very first call (no conversation yet) extracts the outline
    # from the uploaded InDesign JSON; later calls carry an edit instruction.
    instruction: Optional[str] = Field(default=None, max_length=8000)
    conversation_id: Optional[uuid.UUID] = None
    # Optional saved preset of reusable formatting rules to apply.
    preset_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class OutlineRefineResponse(BaseModel):
    conversation_id: uuid.UUID
    # Full re-produced outline; shape matches what /presentation/prepare accepts.
    outlines: List[SlideOutlineModel]
    summary: str

    model_config = ConfigDict(extra="forbid")


class OutlinePreset(BaseModel):
    id: str
    name: str
    rules: str

    model_config = ConfigDict(extra="forbid")


class SavePresetRequest(BaseModel):
    presentation_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    conversation_id: Optional[uuid.UUID] = None
    # If omitted, rules are auto-summarized from the refinement conversation.
    rules: Optional[str] = Field(default=None, max_length=8000)

    model_config = ConfigDict(extra="forbid")
