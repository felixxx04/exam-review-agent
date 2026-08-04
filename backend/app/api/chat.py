from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.middleware import PromptInjectionGuard
from app.db.database import get_db
from app.orchestrator.graph import run_orchestrator
from app.schemas.chat import ChatRequest
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _guard_prompt(request: ChatRequest) -> ChatRequest:
    if not PromptInjectionGuard.check(request.message):
        raise HTTPException(status_code=400, detail="Suspicious input detected")
    return request


@router.post("")
async def chat(
    request: ChatRequest = Depends(_guard_prompt),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = MemoryService(db)
    if request.conversation_id:
        conversation = await memory.get_conversation(
            current_user.id, request.conversation_id
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        conversation = await memory.get_or_create_active_conversation(current_user.id)

    async def event_stream():
        try:
            conversation_id = conversation.id

            yield f"data: {json.dumps({'event': 'conversation', 'data': {'id': conversation_id}}, ensure_ascii=False)}\n\n"

            await memory.save_message(
                user_id=current_user.id,
                conversation_id=conversation_id,
                role="user",
                content=request.message,
                material_scope=request.material_scope,
                metadata={"mode": "ask"},
            )
            memory_context = await memory.build_memory_context(
                conversation_id=conversation_id,
                user_id=current_user.id,
                material_scope=request.material_scope,
            )
            await db.rollback()

            result = await run_orchestrator(
                message=request.message,
                user_id=current_user.subject,
                material_scope=request.material_scope,
                memory_context=memory_context,
            )
            messages = result.get("messages", [])
            citations = result.get("citations")
            quiz = result.get("quiz")
            assistant_content = ""
            for msg in messages:
                if hasattr(msg, "content"):
                    content = msg.content
                    if msg.__class__.__name__ == "AIMessage":
                        assistant_content = content
                        for char in content:
                            chunk = json.dumps(
                                {"event": "token", "data": char}, ensure_ascii=False
                            )
                            yield f"data: {chunk}\n\n"
                        yield f"data: {json.dumps({'event': 'done', 'data': content, 'citations': citations, 'quiz': quiz}, ensure_ascii=False)}\n\n"
                    else:
                        yield f"data: {json.dumps({'event': 'message', 'data': content}, ensure_ascii=False)}\n\n"
            if assistant_content:
                await memory.save_message(
                    user_id=current_user.id,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_content,
                    material_scope=request.material_scope,
                    metadata={"mode": "ask", "citations": citations or []},
                )
        except Exception:
            logger.exception("Chat stream failed")
            try:
                await db.rollback()
            except Exception:
                pass
            yield f"data: {json.dumps({'event': 'error', 'error': '聊天服务暂时不可用'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
