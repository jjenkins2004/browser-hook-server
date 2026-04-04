from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Security
from contextlib import asynccontextmanager
from supabase import create_async_client


from app.db.client import init_supabase_client
from app.config import keys

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler()],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_supabase_client()
    yield
    # Any Cleanup after app shutdown


app = FastAPI(
    title="BrowserHook",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== Global Endpoints ======


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ====== Include routes ======


