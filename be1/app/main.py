import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .graph import graph
from .schemas import ChatRequest
from .turnlog import log_turn

app = FastAPI(title="DMX Advisor BE1")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest):
    config = {"configurable": {"thread_id": req.session_id}}

    async def gen():
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
