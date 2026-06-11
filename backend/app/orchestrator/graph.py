from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph

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


async def handle_qa_node(state: AgentState) -> dict[str, Any]:
    """Placeholder for RAG-based question answering."""
    return {"messages": [AIMessage(content="QA handling in progress")]}


async def handle_quiz_node(state: AgentState) -> dict[str, Any]:
    """Placeholder for quiz generation."""
    return {"messages": [AIMessage(content="Quiz generation in progress")]}


async def handle_review_node(state: AgentState) -> dict[str, Any]:
    """Placeholder for mistake review."""
    return {"messages": [AIMessage(content="Review handling in progress")]}


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
    initial_state: dict[str, Any] = {
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "user_id": user_id,
    }
    initial_state.update(kwargs)
    result = await orchestrator.ainvoke(initial_state)
    return result
