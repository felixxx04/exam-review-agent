from __future__ import annotations

import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, ConversationMessage, LearningProfile, MessageRole, User


DEFAULT_USER_NAME = "Default User"
RECENT_MESSAGE_LIMIT = 12
SUMMARY_MESSAGE_INTERVAL = 6


class MemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_default_user(self, user_id: str = "default") -> User:
        result = await self.db.execute(
            select(User).where(User.email == f"{user_id}@example.local")
        )
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        user = User(
            email=f"{user_id}@example.local",
            hashed_password="local-memory-user",
            display_name=DEFAULT_USER_NAME,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_or_create_active_conversation(
        self, user_id: str = "default"
    ) -> Conversation:
        user = await self.get_or_create_default_user(user_id)
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            return conversation

        conversation = Conversation(user_id=user.id, title="默认复习会话")
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def create_conversation(
        self,
        user_id: str = "default",
        title: str = "新的复习会话",
    ) -> Conversation:
        user = await self.get_or_create_default_user(user_id)
        conversation = Conversation(user_id=user.id, title=title)
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def get_or_create_learning_profile(
        self, user_id: str = "default"
    ) -> LearningProfile:
        user = await self.get_or_create_default_user(user_id)
        result = await self.db.execute(
            select(LearningProfile).where(LearningProfile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()
        if profile is not None:
            return profile

        profile = LearningProfile(
            user_id=user.id,
            weak_concepts=[],
            frequent_questions=[],
            active_materials=[],
            preferences={},
        )
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        material_scope: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole(role),
            content=content,
            material_scope=material_scope,
            message_metadata=metadata or {},
        )
        conversation = await self.db.get(Conversation, conversation_id)
        if conversation is not None:
            now = datetime.datetime.now(datetime.UTC)
            conversation.message_count = (conversation.message_count or 0) + 1
            conversation.last_message_at = now
            conversation.updated_at = now
            conversation.material_scope = material_scope
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_recent_messages(
        self,
        conversation_id: int,
        limit: int = RECENT_MESSAGE_LIMIT,
    ) -> list[ConversationMessage]:
        result = await self.db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def build_memory_context(
        self,
        conversation_id: int,
        user_id: str = "default",
        material_scope: list[str] | None = None,
    ) -> dict[str, Any]:
        conversation = await self.db.get(Conversation, conversation_id)
        profile = await self.get_or_create_learning_profile(user_id)
        recent = await self.get_recent_messages(conversation_id)
        return {
            "conversation_id": conversation_id,
            "summary": conversation.summary if conversation else None,
            "recent_messages": [
                {
                    "role": self._role_value(message.role),
                    "content": message.content,
                }
                for message in recent
            ],
            "learning_profile": self.profile_to_dict(profile),
            "material_scope": material_scope or [],
        }

    def should_update_summary(self, conversation: Conversation) -> bool:
        return (
            conversation.message_count > 0
            and conversation.message_count % SUMMARY_MESSAGE_INTERVAL == 0
        )

    async def merge_learning_profile(
        self,
        profile: LearningProfile,
        extracted: dict[str, Any],
    ) -> LearningProfile:
        if isinstance(extracted.get("current_subject"), str) and extracted[
            "current_subject"
        ].strip():
            profile.current_subject = extracted["current_subject"].strip()
        if isinstance(extracted.get("review_goal"), str) and extracted[
            "review_goal"
        ].strip():
            profile.review_goal = extracted["review_goal"].strip()
        profile.weak_concepts = self._merge_list(
            profile.weak_concepts,
            extracted.get("weak_concepts"),
        )
        profile.frequent_questions = self._merge_list(
            profile.frequent_questions,
            extracted.get("frequent_questions"),
            limit=10,
        )
        profile.active_materials = self._merge_list(
            profile.active_materials,
            extracted.get("active_materials"),
            limit=20,
        )
        if isinstance(extracted.get("preferences"), dict):
            profile.preferences = {
                **(profile.preferences or {}),
                **extracted["preferences"],
            }
        profile.updated_at = datetime.datetime.now(datetime.UTC)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    def to_langchain_messages(
        self,
        memory_context: dict[str, Any],
        current_message: str,
    ) -> list:
        system_parts = []
        learning_profile = memory_context.get("learning_profile") or {}
        if learning_profile:
            system_parts.append(f"用户学习状态: {learning_profile}")
        if memory_context.get("summary"):
            system_parts.append(f"本会话摘要: {memory_context['summary']}")

        messages = []
        if system_parts:
            messages.append(SystemMessage(content="\n".join(system_parts)))
        for item in memory_context.get("recent_messages", []):
            if item["role"] == "assistant":
                messages.append(AIMessage(content=item["content"]))
            elif item["role"] == "user":
                messages.append(HumanMessage(content=item["content"]))
        messages.append(HumanMessage(content=current_message))
        return messages

    @staticmethod
    def profile_to_dict(profile: LearningProfile) -> dict[str, Any]:
        return {
            "current_subject": profile.current_subject,
            "review_goal": profile.review_goal,
            "weak_concepts": profile.weak_concepts or [],
            "frequent_questions": profile.frequent_questions or [],
            "active_materials": profile.active_materials or [],
            "preferences": profile.preferences or {},
        }

    @staticmethod
    def _merge_list(existing: list | None, incoming: Any, limit: int = 20) -> list:
        merged = list(existing or [])
        if not isinstance(incoming, list):
            return merged[:limit]
        for value in incoming:
            if isinstance(value, str):
                normalized = value.strip()
                if normalized and normalized not in merged:
                    merged.append(normalized)
        return merged[-limit:]

    @staticmethod
    def _role_value(role: str | MessageRole) -> str:
        return role.value if hasattr(role, "value") else str(role)
