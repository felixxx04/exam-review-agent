import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph

from app.agents.rag_agent import RAGAgent
from app.agents.quiz_agent import QuizAgent
from app.agents.tracker_agent import TrackerAgent
from app.core.store import get_shared_store
from app.schemas.quiz import to_quiz_payload
from app.services.llm_service import get_default_llm_service
from app.services.retrieval_service import RetrievalService
from app.specialists.quiz_generator import QuizGenerator

from .router import classify_intent
from .state import AgentState


def route_intent_node(state: AgentState) -> dict[str, Any]:
    """Extract the last user message and classify the intent."""
    messages = state["messages"]
    last_message = messages[-1] if messages else ""
    content = last_message if isinstance(last_message, str) else last_message.content
    intent = classify_intent(content)
    return {"intent": intent}


def router(state: AgentState) -> str:
    """Return the intent label used for conditional edges."""
    return state["intent"]


def _build_rag_agent() -> RAGAgent:
    llm = get_default_llm_service()
    retrieval = RetrievalService()
    return RAGAgent(llm_service=llm, retrieval_service=retrieval)


def _build_quiz_agent() -> QuizAgent:
    llm = get_default_llm_service()
    retrieval = RetrievalService()
    generator = QuizGenerator(llm)
    tracker = TrackerAgent(db=get_shared_store(), llm_service=llm)
    return QuizAgent(retrieval, generator, tracker_agent=tracker)


def _build_tracker_agent() -> TrackerAgent:
    llm = get_default_llm_service()
    return TrackerAgent(db=get_shared_store(), llm_service=llm)


def _get_last_user_message(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1] if messages else ""
    return last_message if isinstance(last_message, str) else last_message.content


def _extract_quiz_count(message: str, default: int = 5) -> int:
    digit_match = re.search(r"(\d+)\s*道", message)
    if digit_match:
        return max(1, min(int(digit_match.group(1)), 10))

    chinese_map = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    chinese_match = re.search(r"([一二两三四五六七八九十])\s*道", message)
    if chinese_match:
        return chinese_map.get(chinese_match.group(1), default)

    return default


def _derive_quiz_topic(message: str) -> str:
    topic = message
    patterns = [
        r"给我",
        r"请",
        r"帮我",
        r"基于",
        r"根据",
        r"围绕",
        r"关于",
        r"\d+\s*道",
        r"[一二两三四五六七八九十]\s*道",
        r"几道",
        r"选择题",
        r"填空题",
        r"题目",
        r"出题",
        r"出",
        r"生成",
        r"来",
        r"做",
        r"测验",
        r"测试一下",
        r"测试我",
        r"考考我",
        r"quiz",
    ]
    for pattern in patterns:
        topic = re.sub(pattern, " ", topic, flags=re.IGNORECASE)

    topic = " ".join(topic.split()).strip("，。！？,. ")
    return topic or "核心概念 重点知识"


def _summarize_review(concepts: list[dict]) -> str:
    if not concepts:
        return "目前还没有可用的错题记录。先完成几道测验题，我们就能开始分析薄弱点。"

    top_concepts = concepts[:3]
    lines = ["我根据当前错题记录整理了这些薄弱点："]
    for item in top_concepts:
        lines.append(
            f"- {item['concept'] or '未命名知识点'}：错误 {item['attempt_count']} 次"
        )
    return "\n".join(lines)


async def handle_qa_node(state: AgentState) -> dict[str, Any]:
    """Answer a question against uploaded materials."""
    question = _get_last_user_message(state)
    agent = _build_rag_agent()
    response = await agent.answer(
        question=question,
        user_id=state["user_id"],
        material_scope=state.get("material_scope"),
    )
    return {
        "messages": [AIMessage(content=response.content)],
        "citations": response.citations,
    }


async def handle_quiz_node(state: AgentState) -> dict[str, Any]:
    """Generate quiz questions from uploaded materials."""
    message = _get_last_user_message(state)
    count = _extract_quiz_count(message)
    topic = _derive_quiz_topic(message)
    difficulty = 0.5

    agent = _build_quiz_agent()
    response = await agent.generate_quiz(
        user_id=state["user_id"],
        topic=topic,
        difficulty=difficulty,
        count=count,
        material_scope=state.get("material_scope"),
    )
    quiz_payload = to_quiz_payload(response, difficulty=difficulty)

    if quiz_payload["total"] == 0:
        content = "暂时没能从当前资料里提取出可用题目。请确认资料已经处理完成，或换一个更具体的知识点再试一次。"
    else:
        content = f"已根据当前资料生成 {quiz_payload['total']} 道题，正在切换到测验模式。"

    return {
        "messages": [AIMessage(content=content)],
        "quiz": quiz_payload,
    }


async def handle_review_node(state: AgentState) -> dict[str, Any]:
    """Summarize the user's current weak points."""
    tracker = _build_tracker_agent()
    concepts = await tracker.get_weak_concepts(state["user_id"])
    return {"messages": [AIMessage(content=_summarize_review(concepts))]}


# Build the StateGraph
graph = StateGraph(AgentState)

graph.add_node("route_intent", route_intent_node)
graph.add_node("handle_qa", handle_qa_node)
graph.add_node("handle_quiz", handle_quiz_node)
graph.add_node("handle_review", handle_review_node)

graph.set_entry_point("route_intent")

graph.add_conditional_edges(
    "route_intent",
    router,
    {
        "qa": "handle_qa",
        "quiz": "handle_quiz",
        "review": "handle_review",
    },
)

orchestrator = graph.compile()


async def run_orchestrator(message: str, user_id: str, **kwargs: Any) -> dict[str, Any]:
    """Convenience function to run the orchestrator with a single message.

    Args:
        message: The user's input message.
        user_id: Identifier for the user.
        **kwargs: Additional fields to include in the initial state
            (e.g. material_scope, active_session).

    Returns:
        The final state dict after the graph has executed.
    """
    memory_context = kwargs.pop("memory_context", None)
    initial_state: dict[str, Any] = {
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "user_id": user_id,
    }
    if memory_context is not None:
        initial_state["memory_context"] = memory_context
    initial_state.update(kwargs)
    result = await orchestrator.ainvoke(initial_state)
    if memory_context is not None and "memory_context" not in result:
        result["memory_context"] = memory_context
    return result
