import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from db import elasticsearch, qdrant

from .graph import graph
from .adaptive_api import router as adaptive_router
from .schemas import ChatRequest
from .tracing import set_session
from .turnlog import log_turn


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await elasticsearch.start()
    await qdrant.start()
    try:
        yield
    finally:
        await qdrant.close()
        await elasticsearch.close()


app = FastAPI(title="DMX Advisor BE1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(adaptive_router)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest):
    config = {"configurable": {"thread_id": req.session_id}}

    async def gen():
        set_session(req.session_id)
        events: list[dict] = []
        try:
            async for payload in graph.astream(
                {"user_input": req.message}, config, stream_mode="custom"
            ):
                events.append(payload)
                if not payload["type"].startswith("_"):  # "_..." = internal, log-only
                    yield {"event": payload["type"], "data": json.dumps(payload, ensure_ascii=False)}
        finally:
            log_turn(req.session_id, req.message, events)

    return EventSourceResponse(gen())
