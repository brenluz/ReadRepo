from collections.abc import Iterable

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.chunking import Chunk
from app.embeddings import CodeEmbeddings


def _chunks_to_documents(chunks: Iterable[Chunk]) -> list[Document]:
    # Chroma metadata values must be str/int/float/bool - never None - so
    # the optional language is coerced to an empty string.
    return [
        Document(
            page_content=chunk["content"],
            metadata={
                "path": chunk["path"],
                "category": chunk["category"],
                "language": chunk["language"] or "",
                "chunk_type": chunk["chunk_type"],
            },
        )
        for chunk in chunks
    ]


def build_vector_store(
    chunks: Iterable[Chunk],
    persist_directory: str | None = None,
    collection_name: str = "repo",
) -> Chroma:
    """
    Embeds chunks and stores them in a Chroma collection. With
    persist_directory set, Chroma writes to that folder (reloadable
    later); without it, the store lives only in memory.
    """
    return Chroma.from_documents(
        documents=_chunks_to_documents(chunks),
        embedding=CodeEmbeddings(),
        persist_directory=persist_directory,
        collection_name=collection_name,
    )


def search(
    store: Chroma,
    query: str,
    k: int = 5,
    category: str | None = None,
) -> list[Document]:
    where = {"category": category} if category else None
    return store.similarity_search(query, k=k, filter=where)
