import os
import shutil
import time
from pathlib import Path

from langchain_chroma import Chroma

from app.chunking import chunk_repo_files
from app.config import settings
from app.embeddings import CodeEmbeddings
from app.github_client import fetch_commit_sha
from app.repo_files import fetch_repo_files
from app.vector_store import build_vector_store

_COLLECTION_NAME = "repo"


class RepoTooLargeError(Exception):
    """Repo would produce more chunks than we're willing to embed on CPU."""

    def __init__(self, chunk_count: int, limit: int) -> None:
        self.chunk_count = chunk_count
        self.limit = limit
        super().__init__(f"{chunk_count} chunks exceeds the local limit of {limit}")


def _cache_root() -> Path:
    root = Path(settings.embedding_cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _entry_dir(owner: str, repo: str, sha: str) -> Path:
    key = f"{owner}__{repo}__{sha}"
    return _cache_root() / key


def _ttl_seconds() -> float:
    return settings.embedding_cache_ttl_hours * 3600


def _is_fresh(path: Path) -> bool:
    return (time.time() - path.stat().st_mtime) < _ttl_seconds()


def _touch(path: Path) -> None:
    now = time.time()
    os.utime(path, (now, now))  # sliding TTL: reset the clock on each access


def _sweep_expired() -> None:
    for entry in _cache_root().iterdir():
        if entry.is_dir() and not _is_fresh(entry):
            shutil.rmtree(entry, ignore_errors=True)


async def get_repo_store(
    owner: str,
    repo: str,
    access_token: str | None = None,
    ref: str | None = None,
) -> Chroma:
    """
    Returns a Chroma store of the repo's embedded chunks, built fresh on a
    cache miss (fetch -> chunk -> embed -> persist) or reloaded from disk on
    a hit. Keyed by the current commit SHA so new commits re-embed; entries
    past the sliding TTL are swept opportunistically.
    """
    _sweep_expired()
    sha = await fetch_commit_sha(owner, repo, access_token, ref)
    entry = _entry_dir(owner, repo, sha)
    embeddings = CodeEmbeddings()

    if entry.exists() and _is_fresh(entry):
        try:
            store = Chroma(
                persist_directory=str(entry),
                embedding_function=embeddings,
                collection_name=_COLLECTION_NAME,
            )
            if store._collection.count() == 0:
                # An interrupted build leaves an empty collection behind;
                # treat it as a miss rather than serving zero results.
                raise RuntimeError("empty cache entry")
            _touch(entry)
            return store
        except Exception:
            # Corrupt/partial entry (e.g. a prior build crashed mid-write):
            # discard it and fall through to a clean rebuild.
            shutil.rmtree(entry, ignore_errors=True)

    files = await fetch_repo_files(owner, repo, access_token, ref)
    chunks = list(chunk_repo_files(files))
    if len(chunks) > settings.max_repo_chunks:
        raise RepoTooLargeError(len(chunks), settings.max_repo_chunks)
    store = build_vector_store(
        chunks,
        persist_directory=str(entry),
        collection_name=_COLLECTION_NAME,
    )
    _touch(entry)
    return store
