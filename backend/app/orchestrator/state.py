from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages
from typing_extensions import NotRequired


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    user_id: str
    material_scope: NotRequired[list[str] | None]
    active_session: NotRequired[dict | None]
    citations: NotRequired[list[dict]]
    quiz: NotRequired[dict | None]
    memory_context: NotRequired[dict[str, Any]]
