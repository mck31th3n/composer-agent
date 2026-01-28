"""Pydantic models for patch plan schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DiffRef(BaseModel):
    """Reference to a diff entry."""

    model_config = ConfigDict(extra="forbid")

    type: str
    measure: int
    beat: float


class PatchParams(BaseModel):
    """Operation parameters."""

    model_config = ConfigDict(extra="forbid")

    pitch_midi: int | None = Field(default=None, ge=0, le=127)
    duration: float | None = Field(default=None, gt=0)
    old_pitch_midi: int | None = Field(default=None, ge=0, le=127)
    old_duration: float | None = Field(default=None, gt=0)


class PatchOperation(BaseModel):
    """A single patch operation."""

    model_config = ConfigDict(extra="forbid")

    op_id: str
    diff_ref: DiffRef | None = None
    type: Literal["insert_note", "delete_note", "update_duration", "update_pitch", "noop"]
    measure: int
    beat: float
    voice: int = Field(default=1, ge=1)
    params: PatchParams = Field(default_factory=PatchParams)


class PatchPlan(BaseModel):
    """Patch plan root object."""

    model_config = ConfigDict(extra="forbid")

    source_file: str
    source_diff_timestamp: str
    operations: list[PatchOperation]
