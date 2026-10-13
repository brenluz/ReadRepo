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

    # Optional: only needed for the (dormant) OAuth login flow. Repo
    # fetching works unauthenticated, so the app runs without these.
    github_client_id: str | None = None
    github_client_secret: str | None = None
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
    # Cap the tokens actually embedded (the full chunk text is still stored
    # for the LLM). The model supports 8192, but embedding cost scales with
    # length; 512 measured ~2.6x faster than full with no retrieval-quality
    # loss, since a chunk's identifying signal is front-loaded.
    embedding_max_seq_tokens: int = 512

    # Per-repo embedding cache. Keyed by owner/repo@commit-sha so new
    # commits re-embed automatically; entries past the sliding TTL (reset
    # on each access) are swept opportunistically. Default location is a
    # disposable per-user cache dir, not the project tree.
    embedding_cache_dir: str = str(
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ReadRepo" / "cache"
    )
    embedding_cache_ttl_hours: float = 24.0

    # Generation. Local LLM via Ollama, kept behind a swappable LangChain
    # chat interface. Low temperature for factual, grounded answers. k is
    # how many retrieved chunks are fed to the model as context.
    llm_model: str = "qwen2.5:3b"
    llm_temperature: float = 0.1
    ollama_base_url: str = "http://localhost:11434"
    retrieval_k: int = 5
    # Ollama defaults to a 2048-token context window; our retrieved chunks
    # plus the prompt can exceed that and be silently truncated, so set it
    # explicitly to comfortably fit k chunks of context.
    llm_num_ctx: int = 8192

    class Config:
        env_file = ".env"


settings = Settings()