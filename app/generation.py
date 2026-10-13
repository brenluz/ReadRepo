from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
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


async def answer_question(
    owner: str,
    repo: str,
    question: str,
    ref: str | None = None,
    access_token: str | None = None,
) -> dict:
    """
    Answers a question about a repo: loads (or builds) its vector store,
    retrieves the most relevant chunks, and has the LLM answer grounded in
    them. Citations are returned from the retrieved chunks themselves, not
    inferred from the model's text, so attribution is reliable.
    """
    store = await get_repo_store(owner, repo, access_token, ref)
    docs = search(store, question, k=settings.retrieval_k)

    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
    chain = prompt | build_llm()
    response = await chain.ainvoke(
        {"question": question, "context": _format_context(docs)}
    )

    sources = sorted({doc.metadata.get("path", "unknown") for doc in docs})
    return {"answer": response.content, "sources": sources}
