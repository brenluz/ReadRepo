import asyncio
from collections.abc import AsyncIterator

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import ChatOllama

from app.config import settings
from app.repo_index import get_repo_store
from app.vector_store import search

_SYSTEM = """You are a code assistant answering questions about a specific GitHub \
repository. Answer using ONLY the provided context, which consists of excerpts from the \
repository's files. Each excerpt is labelled with its file path.

Rules:
- Base your answer only on the context. If the context does not contain the answer, say \
you could not find it in the repository rather than guessing.
- Cite the file path(s) your answer draws from, inline, like (src/pkg/sessions.py).
- Be concise and concrete; refer to the actual functions, classes, and names in the context."""

_HUMAN = """Question: {question}

Context:
{context}"""

_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        MessagesPlaceholder("history"),
        ("human", _HUMAN),
    ]
)


def build_llm() -> BaseChatModel:
    # The swappable seam: ChatOllama today; any LangChain chat model
    # (e.g. ChatAnthropic) could drop in here without touching the rest.
    return ChatOllama(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        base_url=settings.ollama_base_url,
        num_ctx=settings.llm_num_ctx,
    )


def _format_context(docs: list[Document]) -> str:
    blocks = [
        f"--- {doc.metadata.get('path', 'unknown')} ---\n{doc.page_content}"
        for doc in docs
    ]
    return "\n\n".join(blocks)


def _sources(docs: list[Document]) -> list[str]:
    # Citations come from the retrieved chunks, not the model's text.
    return sorted({doc.metadata.get("path", "unknown") for doc in docs})


def _last_user_text(history: list[BaseMessage]) -> str | None:
    for message in reversed(history):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return None


async def _retrieve(
    owner: str,
    repo: str,
    question: str,
    history: list[BaseMessage],
    ref: str | None,
    access_token: str | None,
) -> list[Document]:
    store = await get_repo_store(owner, repo, access_token, ref)
    # Cheap history-awareness: prepend the previous user turn so referential
    # follow-ups ("what about its error handling?") retrieve sensibly, with
    # no extra LLM call. (A full query-rewrite step is a future enhancement.)
    query = question
    previous = _last_user_text(history) if history else None
    if previous:
        query = f"{previous}\n{question}"
    return search(store, query, k=settings.retrieval_k)


def _invoke_payload(question: str, docs: list[Document], history: list[BaseMessage]) -> dict:
    return {
        "question": question,
        "context": _format_context(docs),
        "history": history[-settings.conversation_max_messages:],
    }


async def answer_question(
    owner: str,
    repo: str,
    question: str,
    history: list[BaseMessage] | None = None,
    ref: str | None = None,
    access_token: str | None = None,
) -> dict:
    """
    Answers a question grounded in retrieved repo chunks, optionally using
    prior conversation history. Citations come from the retrieved chunks.
    """
    history = history or []
    docs = await _retrieve(owner, repo, question, history, ref, access_token)
    chain = _PROMPT | build_llm()
    response = await chain.ainvoke(_invoke_payload(question, docs, history))
    return {"answer": response.content, "sources": _sources(docs)}


async def stream_answer(
    owner: str,
    repo: str,
    question: str,
    history: list[BaseMessage] | None = None,
    ref: str | None = None,
    access_token: str | None = None,
) -> AsyncIterator[dict]:
    """
    Streams the same answer as events: a 'status' before the (possibly slow)
    retrieval/embed, then 'token' events as the model writes, then a final
    'sources' event. The route accumulates tokens into the full answer.
    """
    history = history or []
    yield {"type": "status", "text": "Preparing repository index..."}

    # Retrieval may trigger a slow one-time embed. Run it as a task and emit
    # heartbeats while it works, so the stream stays alive (keeping the
    # extension's background worker awake) and the user sees progress.
    retrieve_task = asyncio.create_task(
        _retrieve(owner, repo, question, history, ref, access_token)
    )
    waited = 0.0
    while not retrieve_task.done():
        done, _ = await asyncio.wait(
            {retrieve_task}, timeout=settings.stream_heartbeat_seconds
        )
        if not done:
            waited += settings.stream_heartbeat_seconds
            yield {
                "type": "status",
                "text": f"Indexing repository… one-time, still working ({int(waited)}s)",
            }
    docs = retrieve_task.result()

    yield {"type": "status", "text": "Generating answer…"}
    chain = _PROMPT | build_llm()
    async for chunk in chain.astream(_invoke_payload(question, docs, history)):
        if chunk.content:
            yield {"type": "token", "text": chunk.content}

    yield {"type": "sources", "sources": _sources(docs)}
