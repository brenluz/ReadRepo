import uuid

from langchain_core.messages import BaseMessage


class ConversationStore:
    """
    In-memory chat history keyed by conversation id. Same deliberately
    simple pattern as SessionStore: fine for a local single-user tool,
    lost on restart. Swap for a persistent store later if needed.
    """

    def __init__(self) -> None:
        self._data: dict[str, list[BaseMessage]] = {}

    def create(self) -> str:
        conversation_id = uuid.uuid4().hex
        self._data[conversation_id] = []
        return conversation_id

    def get(self, conversation_id: str) -> list[BaseMessage] | None:
        return self._data.get(conversation_id)

    def append(self, conversation_id: str, *messages: BaseMessage) -> None:
        self._data.setdefault(conversation_id, []).extend(messages)


conversation_store = ConversationStore()
