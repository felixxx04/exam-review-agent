from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import NotRequired

from typing import TypedDict


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    user_id: str
    material_scope: NotRequired[list[str] | None]
    active_session: NotRequired[dict | None]
