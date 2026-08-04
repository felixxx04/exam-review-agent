from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.database import get_db
from app.db.models import Conversation
from app.schemas.common import ApiResponse
from app.schemas.conversations import (
    ConversationListResponse,
    ConversationMessageResponse,
    ConversationMessagesResponse,
    ConversationResponse,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MemoryService(db)
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    conversations = list(result.scalars().all())
    conversations = [
        await service.autotitle_default_conversation(conversation)
        for conversation in conversations
    ]
    return ApiResponse.ok(
        data=ConversationListResponse(
            conversations=conversations,
            total=len(conversations),
        ),
        meta={"total": len(conversations)},
    )


@router.get("/active")
async def get_active_conversation(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MemoryService(db)
    conversation = await service.get_or_create_active_conversation(current_user.id)
    return ApiResponse.ok(data=ConversationResponse.model_validate(conversation))


@router.post("")
async def create_conversation(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MemoryService(db)
    conversation = await service.create_conversation(current_user.id)
    return ApiResponse.ok(data=ConversationResponse.model_validate(conversation))


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    await db.delete(conversation)
    await db.commit()
    return ApiResponse.ok(data={"detail": "已删除"})


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MemoryService(db)
    conversation = await service.get_conversation(current_user.id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = await service.get_recent_messages(
        current_user.id, conversation_id, limit=100
    )
    data = ConversationMessagesResponse(
        conversation_id=conversation_id,
        messages=[
            ConversationMessageResponse(
                id=message.id,
                conversation_id=message.conversation_id,
                role=service._role_value(message.role),
                content=message.content,
                material_scope=message.material_scope,
                metadata=message.message_metadata or {},
                created_at=message.created_at,
            )
            for message in messages
        ],
    )
    return ApiResponse.ok(data=data)
