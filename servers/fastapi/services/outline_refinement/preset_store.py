"""Persistence for reusable outline-refinement presets.

A preset captures content-agnostic transformation rules (structure/style)
distilled from a refinement chat, so the same rules can be re-applied to a
different document (e.g. the next textbook unit). Stored as a single JSON row
in the generic KeyValue table, mirroring how themes are stored.
"""

import copy
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.sql.key_value import KeyValueSqlModel

PRESETS_STORAGE_KEY = "outline_refine_presets"


async def _get_row(sql_session: AsyncSession) -> Optional[KeyValueSqlModel]:
    return await sql_session.scalar(
        select(KeyValueSqlModel).where(KeyValueSqlModel.key == PRESETS_STORAGE_KEY)
    )


def _read_presets(row: Optional[KeyValueSqlModel]) -> list[dict[str, Any]]:
    if not row:
        return []
    value = row.value if isinstance(row.value, dict) else {}
    presets = value.get("presets", [])
    return copy.deepcopy(presets) if isinstance(presets, list) else []


async def list_presets(sql_session: AsyncSession) -> list[dict[str, Any]]:
    return _read_presets(await _get_row(sql_session))


async def get_preset(
    sql_session: AsyncSession, preset_id: str
) -> Optional[dict[str, Any]]:
    return next(
        (p for p in await list_presets(sql_session) if p.get("id") == preset_id),
        None,
    )


async def save_preset(
    sql_session: AsyncSession, *, name: str, rules: str
) -> dict[str, Any]:
    row = await _get_row(sql_session)
    presets = _read_presets(row)

    preset = {"id": str(uuid.uuid4()), "name": name.strip(), "rules": rules.strip()}
    presets.append(preset)

    if row:
        row.value = {"presets": presets}
        sql_session.add(row)
    else:
        sql_session.add(
            KeyValueSqlModel(key=PRESETS_STORAGE_KEY, value={"presets": presets})
        )
    await sql_session.commit()
    return preset


async def delete_preset(sql_session: AsyncSession, preset_id: str) -> bool:
    row = await _get_row(sql_session)
    presets = _read_presets(row)
    remaining = [p for p in presets if p.get("id") != preset_id]
    if len(remaining) == len(presets):
        return False
    if row:
        row.value = {"presets": remaining}
        sql_session.add(row)
        await sql_session.commit()
    return True
