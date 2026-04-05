from app.models.db import Tables

from .functions import delete, get, insert, update, upsert

__all__ = ["Tables", "insert", "upsert", "get", "update", "delete"]
