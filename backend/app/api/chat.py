from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.middleware import PromptInjectionGuard
from app.orchestrator.graph import run_orchestrator
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _guard_prompt(request: ChatRequest) -> ChatRequest:
    if not PromptInjectionGuard.check(request.message):
        raise HTTPException(status_code=400, detail="Suspicious input detected")
    return request


@router.post("")
async def chat(request: ChatRequest = Depends(_guard_prompt)):
    async def event_stream():
        try:
            result = await run_orchestrator(
                message=request.message,
                user_id="default",
                material_scope=request.material_scope,
            )
            messages = result.get("messages", [])
            for msg in messages:
                if hasattr(msg, "content"):
                    content = msg.content
                    if msg.__class__.__name__ == "AIMessage":
                        for char in content:
                            chunk = json.dumps(
                                {"event": "token", "data": char}, ensure_ascii=False
                            )
                            yield f"data: {chunk}\n\n"
                        yield f"data: {json.dumps({'event': 'done', 'data': content}, ensure_ascii=False)}\n\n"
                    else:
                        yield f"data: {json.dumps({'event': 'message', 'data': content}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
