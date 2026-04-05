from postgrest.types import JSON, CountMethod, ReturnMethod
from pydantic import BaseModel
from fastapi.encoders import jsonable_encoder
from typing import TypeVar, Type, Union, Optional, Any, Sequence

import logging

from app.models.db import Tables

from .client import perform_supabase_operation

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# MARK: Inserting


async def insert(table: Tables, entries: Sequence[BaseModel]) -> None:
    """
    Insert an entry into supabase table following the BaseModel.
    """
    async with perform_supabase_operation("INSERT", table) as supabase:
        if not entries:
            return

        payload = jsonable_encoder(entries, by_alias=False)
        await supabase.table(table).insert(
            payload, returning=ReturnMethod.minimal
        ).execute()


async def upsert(
    table: Tables,
    entries: Sequence[BaseModel],
    on_conflict: Optional[str] = None,
) -> None:
    """
    Upsert entries into a Supabase table following the BaseModel.
    Optionally provide an on_conflict column list (comma-separated) to define conflict targets.
    """
    async with perform_supabase_operation("UPSERT", table) as supabase:
        if not entries:
            return

        payload = jsonable_encoder(entries, by_alias=False)
        if on_conflict is not None:
            query = supabase.table(table).upsert(
                payload,
                returning=ReturnMethod.minimal,
                on_conflict=on_conflict,
            )
        else:
            query = supabase.table(table).upsert(
                payload,
                returning=ReturnMethod.minimal,
            )
        await query.execute()


# MARK: Getting


async def get(
    table: Tables,
    filters: dict[str, Union[str, list[str]]],
    model: Type[T],
    joins: Optional[list[Tables]] = None,
) -> list[T]:
    """
    Fetch a row by id with built in parsing.
    For ordering, if descending or ordered_col are left out then there is no ordering
    Joins should be a list of related table names to fetch all columns from.
    Add an entry with the joined table name for the joined data

    Returns data, or empty list if nothing was found.
    """

    async with perform_supabase_operation("GET", table) as supabase:

        # Build select clause including any joins, joined tables have all columns selected
        select_parts = _get_model_columns(model)
        if joins:
            for rel_table in joins:
                try:
                    select_parts.remove(rel_table)
                except ValueError:
                    logger.warning(
                        "Joined table field '{rel_table}' not found in primary model columns."
                    )

                select_parts.append(f"{rel_table}(*)")

        query = supabase.table(table).select(",".join(select_parts))

        # Apply each filter
        for col, value in filters.items():
            if isinstance(value, list):
                query = query.in_(col, value)
            else:
                query = query.eq(col, value)

        resp = await query.execute()

        if not resp.data:
            logger.info("No rows found in %s with filters=%s", table, filters)
            return []

        return [model.model_validate(row) for row in resp.data]


# MARK: Updating


async def update(
    table: Tables,
    updates: dict[str, Any],
    filters: dict[str, Union[str, list[str]]],
):
    """
    Updates one or more columns in a table for entries matching the filters.
    """
    async with perform_supabase_operation("UPDATE", table) as supabase:

        # Check if there's anything to update
        if not updates:
            logger.warning("Update called on table %s with no update values.", table)
            return 0

        # Build the base update operation with the dictionary of new values
        encoded_updates = jsonable_encoder(updates, by_alias=False)
        query = supabase.table(table).update(
            encoded_updates, returning=ReturnMethod.minimal
        )

        # Apply each filter
        for col, value in filters.items():
            if isinstance(value, list):
                query = query.in_(col, value)
            else:
                query = query.eq(col, value)

        await query.execute()


# MARK: Deleting


async def delete(table: Tables, filters: dict[str, Union[str, list[str]]]):
    """
    Delete entries from a table.
    Returns true if rows were deleted, false otherwise.
    """
    async with perform_supabase_operation("DELETE", table) as supabase:

        query = supabase.table(table).delete(returning=ReturnMethod.minimal)

        # Apply each filter
        for col, value in filters.items():
            if isinstance(value, list):
                query = query.in_(col, value)
            else:
                query = query.eq(col, value)

        await query.execute()


# MARK: Private


def _get_model_columns(model_type: Type[BaseModel]) -> list[str]:
    return list(model_type.model_fields.keys())
