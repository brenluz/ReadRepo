import json

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

from app.conversations import conversation_store
from app.generation import answer_question, stream_answer
from app.github_client import (
    ArchiveTooLargeError,
    GithubApiError,
    RateLimitedError,
    RepoNotFoundError,
)
from app.repo_index import RepoTooLargeError

router = APIRouter(prefix="/chat")


class ChatRequest(BaseModel):
    owner: str
    repo: str
    question: str
    conversation_id: str | None = None
    ref: str | None = None


def _resolve_conversation(conversation_id: str | None) -> tuple[str, list[BaseMessage]]:
    if conversation_id:
        existing = conversation_store.get(conversation_id)
        if existing is not None:
            return conversation_id, existing
    return conversation_store.create(), []


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RepoTooLargeError):
        return HTTPException(
            413,
            f"This repository is too large to index locally ({exc.chunk_count} "
            f"chunks, limit {exc.limit}). Try a smaller repository.",
        )
    if isinstance(exc, RepoNotFoundError):
        return HTTPException(404, "Repository not found, inaccessible, or empty")
    if isinstance(exc, RateLimitedError):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return HTTPException(429, "GitHub API rate limit exceeded", headers=headers)
    if isinstance(exc, ArchiveTooLargeError):
        return HTTPException(413, "Repository archive exceeds the size limit")
    if isinstance(exc, httpx.TimeoutException):
        return HTTPException(504, "Timed out fetching the repository from GitHub")
    return HTTPException(502, "Error processing the repository")


@router.post("")
async def chat(req: ChatRequest) -> dict:
    conversation_id, history = _resolve_conversation(req.conversation_id)
    try:
        result = await answer_question(
            req.owner, req.repo, req.question, history=history, ref=req.ref
        )
    except (RepoTooLargeError, GithubApiError, httpx.TimeoutException) as exc:
        raise _http_error(exc)

    conversation_store.append(
        conversation_id, HumanMessage(req.question), AIMessage(result["answer"])
    )
    return {
        "conversation_id": conversation_id,
        "answer": result["answer"],
        "sources": result["sources"],
    }


@router.post("/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    conversation_id, history = _resolve_conversation(req.conversation_id)

    async def events():
        yield json.dumps({"type": "conversation", "conversation_id": conversation_id}) + "\n"
        answer_parts: list[str] = []
        try:
            async for event in stream_answer(
                req.owner, req.repo, req.question, history=history, ref=req.ref
            ):
                if event["type"] == "token":
                    answer_parts.append(event["text"])
                yield json.dumps(event) + "\n"
        except (RepoTooLargeError, GithubApiError, httpx.TimeoutException) as exc:
            detail = _http_error(exc).detail
            yield json.dumps({"type": "error", "detail": detail}) + "\n"
            return

        conversation_store.append(
            conversation_id, HumanMessage(req.question), AIMessage("".join(answer_parts))
        )
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
