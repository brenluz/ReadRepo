import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Centralizes config so it's read from environment variables once,
    validated at startup (fails fast if something's missing), and
    typed (no scattering os.environ[...] calls with no validation
    through the codebase).
    """

    github_client_id: str
    github_client_secret: str
    oauth_redirect_uri: str = "http://localhost:8000/auth/callback"
    oauth_scope: str = "public_repo"

    github_http_timeout_seconds: float = 60.0
    github_max_archive_bytes: int = 300_000_000
    github_max_file_size_bytes: int = 500_000

    # Chunking. Sizes are in tokens; we don't yet have a real tokenizer
    # tied to an embedding model, so token counts are estimated from
    # characters via chunk_chars_per_token (a rough BPE approximation,
    # ~4 chars/token). Revisit once an embedding model is chosen.
    chunk_target_tokens: int = 800
    chunk_overlap_tokens: int = 100
    chunk_chars_per_token: int = 4

    # Embeddings. modernbert-embed-base: local (sentence-transformers),
    # 8192-token context (fits our ~800-token chunks whole), 768-dim.
    # Requires the search_document:/search_query: task prefixes.
    embedding_model: str = "nomic-ai/modernbert-embed-base"
    embedding_document_prefix: str = "search_document: "
    embedding_query_prefix: str = "search_query: "

    # Per-repo embedding cache. Keyed by owner/repo@commit-sha so new
    # commits re-embed automatically; entries past the sliding TTL (reset
    # on each access) are swept opportunistically. Default location is a
    # disposable per-user cache dir, not the project tree.
    embedding_cache_dir: str = str(
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ReadRepo" / "cache"
    )
    embedding_cache_ttl_hours: float = 24.0

    class Config:
        env_file = ".env"


settings = Settings()