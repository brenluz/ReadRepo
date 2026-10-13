# ReadRepo

Ask questions about a public GitHub repository's codebase and get answers grounded in the actual source — with citations to the files each answer came from.

ReadRepo is a retrieval-augmented generation (RAG) pipeline over a repository's contents. It runs locally end to end: repositories are never cloned to disk, and generation uses a local model, so no third-party API keys are required.

## How it works

1. **Fetch** — downloads a repository's contents through the GitHub API as a single in-memory archive. No `git clone`, nothing persisted to disk as source, and one API request regardless of repo size.
2. **Chunk** — splits files with tiered, code-aware chunking: AST-based splitting (via tree-sitter) for ~18 languages so functions and classes stay whole, language-aware heuristics for other languages, and a plain character fallback for everything else. Each chunk is tagged by category (code / docs / config / infra).
3. **Embed** — generates embeddings locally with `modernbert-embed-base` — long-context, CPU-friendly, no API.
4. **Store & cache** — persists vectors in a Chroma store. Embeddings are cached per repository and keyed by commit SHA, so a repo is only re-embedded when it actually changes; cache entries expire on a sliding 24-hour TTL.
5. **Retrieve & answer** — retrieves the most relevant chunks for a question and has a local LLM (served by Ollama) answer strictly from them, citing the source file(s). Citations are derived from the retrieved chunks themselves, not inferred from the model's text. Answers stream token by token, and conversation history is kept so follow-up questions retain context.

A browser extension (`extension/`) surfaces this as a chat panel directly on GitHub repository pages — see `extension/README.md` to load it.

## Tech stack

- **FastAPI** (async) — web backend
- **LangChain** — RAG pipeline orchestration
- **tree-sitter** — code-aware chunking
- **sentence-transformers** (`modernbert-embed-base`) — local embeddings
- **Chroma** — vector store
- **Ollama** — local LLM generation
- **httpx** — async GitHub API access

## Requirements

- Python 3.13 (conda recommended)
- [Ollama](https://ollama.com) with a chat model pulled (default: `qwen2.5:3b`)

## Setup

```bash
pip install -r requirements.txt

# pull the local generation model
ollama pull qwen2.5:3b

# configuration
cp .env.example .env

# run
uvicorn app.main:app --reload
```

## Configuration

Settings are read from environment variables / a `.env` file and validated at startup (see `app/config.py`). Tunable values include the embedding model and input cap, chunk sizes, the cache location and TTL, the Ollama model, and how many chunks are retrieved per question.

## Status

The full flow is implemented end to end: fetch → chunk → embed → store/cache → retrieve → streamed, grounded generation with citations and conversation memory, plus a browser-extension front-end (`extension/`). A possible enhancement is history-aware query rewriting for referential follow-ups.
