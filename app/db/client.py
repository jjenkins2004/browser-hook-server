import logging
from contextlib import asynccontextmanager
from fastapi import HTTPException
from postgrest.exceptions import APIError
from storage3.exceptions import StorageApiError
from httpx import RequestError, ReadTimeout
from supabase import AsyncClient, acreate_client
from pydantic import ValidationError

from app.config import keys


logger = logging.getLogger(__name__)


supabase: AsyncClient | None = None


# Have to add this for outside modules who want to use the client because a copy is made initially and that copy is None
def get_supabase() -> AsyncClient:
    if supabase is None:
        raise HTTPException(status_code=500, detail="Database client uninitialized")
    return supabase


async def init_supabase_client() -> None:
    global supabase
    supabase = await acreate_client(keys.SUPABASE_URL, keys.SUPABASE_KEY)


@asynccontextmanager
async def perform_supabase_operation(
    operation_name: str, table_or_path: str = "unknown"
):
    """
    Centralized error handling context manager for Supabase operations.
    """

    try:
        yield get_supabase()
    except APIError as e:
        msg = e.message or "Unknown database error"
        logger.error("%s error on %s", operation_name, table_or_path, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Database Error: {msg}")
    except StorageApiError as e:
        logger.error(
            "%s storage error on %s", operation_name, table_or_path, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Storage Error: {e.message}")
    except (RequestError, ReadTimeout) as e:
        logger.error(
            "Network error during %s on %s",
            operation_name,
            table_or_path,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=f"Service unavailable: {e}")
    except ValidationError:
        logger.error(
            "Parsing error during %s on %s",
            operation_name,
            table_or_path,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal data parsing error")
    except Exception as e:
        # Catch-all for unexpected bugs
        logger.error(
            "Unexpected error during %s on %s",
            operation_name,
            table_or_path,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")
