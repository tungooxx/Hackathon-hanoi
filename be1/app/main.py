from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import elasticsearch, postgres, qdrant

from .adaptive_api import router as adaptive_router
from .auth.handlers import install_auth_exception_handlers
from .auth.router import router as auth_router
from .chat.handlers import install_chat_exception_handlers
from .chat.router import guest_router, router as chat_router
from .chat.runtime import chat_graph_runtime
from .config import FRONTEND_ORIGINS, validate_auth_config


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    validate_auth_config()
    async with postgres, elasticsearch, qdrant:
        async with chat_graph_runtime:
            yield


app = FastAPI(title="DMX Advisor BE1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
    expose_headers=["Retry-After"],
    max_age=600,
)
install_auth_exception_handlers(app)
install_chat_exception_handlers(app)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(guest_router)
app.include_router(adaptive_router)


@app.get("/health")
async def health():
    return {"ok": True}
