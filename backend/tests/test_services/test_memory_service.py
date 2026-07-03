from __future__ import annotations

import pytest

from app.services.memory_service import MemoryService


@pytest.mark.asyncio
async def test_get_or_create_default_conversation(db_session):
    service = MemoryService(db_session)

    conversation = await service.get_or_create_active_conversation(user_id="default")
    same_conversation = await service.get_or_create_active_conversation(user_id="default")

    assert conversation.id == same_conversation.id
    assert conversation.title == "默认复习会话"


@pytest.mark.asyncio
async def test_save_messages_and_build_context(db_session):
    service = MemoryService(db_session)
    conversation = await service.get_or_create_active_conversation(user_id="default")

    await service.save_message(
        conversation_id=conversation.id,
        role="user",
        content="什么是幻读？",
        material_scope=["database.pdf"],
        metadata={"mode": "ask"},
    )
    await service.save_message(
        conversation_id=conversation.id,
        role="assistant",
        content="幻读是同一事务中再次查询出现新增行。",
        material_scope=["database.pdf"],
        metadata={"citations": [{"source": "database.pdf", "page": 3}]},
    )

    context = await service.build_memory_context(
        conversation_id=conversation.id,
        user_id="default",
        material_scope=["database.pdf"],
    )

    assert context["conversation_id"] == conversation.id
    assert context["learning_profile"]["weak_concepts"] == []
    assert len(context["recent_messages"]) == 2
    assert context["recent_messages"][0]["role"] == "user"
    assert context["recent_messages"][1]["content"] == "幻读是同一事务中再次查询出现新增行。"


@pytest.mark.asyncio
async def test_profile_merge_is_conservative(db_session):
    service = MemoryService(db_session)
    profile = await service.get_or_create_learning_profile(user_id="default")

    await service.merge_learning_profile(
        profile=profile,
        extracted={
            "current_subject": "数据库系统",
            "review_goal": "理解事务隔离级别",
            "weak_concepts": ["幻读", "幻读", "可重复读"],
            "frequent_questions": ["隔离级别区别"],
            "active_materials": ["database.pdf"],
            "preferences": {"answer_style": "examples"},
            "ignored_field": "ignored",
        },
    )

    assert profile.current_subject == "数据库系统"
    assert profile.weak_concepts == ["幻读", "可重复读"]
    assert profile.frequent_questions == ["隔离级别区别"]
    assert profile.active_materials == ["database.pdf"]
    assert profile.preferences == {"answer_style": "examples"}
