from collections.abc import Iterable, Iterator
from typing import TypedDict

from langchain_community.document_loaders.parsers.language.language_parser import (
    LANGUAGE_EXTENSIONS,
    LanguageParser,
)
from langchain_core.document_loaders import Blob
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from app.config import settings
from app.repo_files import RepoFile


class Chunk(TypedDict):
    path: str
    content: str
    category: str         # code | docs | config | infra
    language: str | None  # Language.value if known, else None
    chunk_type: str       # function_class | text


# Tier 1: extensions LanguageParser can split by real AST (function/class
# boundaries). Sourced from LangChain's own map so it tracks upstream.
_TIER1_EXTENSIONS = set(LANGUAGE_EXTENSIONS)

# Tier 2: languages with a heuristic separator preset but no AST segmenter.
_TIER2_EXT_TO_LANGUAGE: dict[str, Language] = {
    "swift": Language.SWIFT,
    "md": Language.MARKDOWN,
    "markdown": Language.MARKDOWN,
    "rst": Language.RST,
    "html": Language.HTML,
    "htm": Language.HTML,
    "tex": Language.LATEX,
    "proto": Language.PROTO,
    "r": Language.R,
    "sol": Language.SOL,
    "hs": Language.HASKELL,
    "ps1": Language.POWERSHELL,
    "vb": Language.VISUALBASIC6,
    "bas": Language.VISUALBASIC6,
}

# Category tagging is heuristic - it exists so a later retrieval step can
# filter/boost by file kind (e.g. surface infra/config only for infra-ish
# questions) without re-chunking. Not meant to be exhaustive.
_INFRA_NAMES = {"dockerfile", "makefile"}
_INFRA_EXTENSIONS = {"tf", "tfvars"}
_CONFIG_NAMES = {"requirements.txt", "pipfile", "gemfile"}
_CONFIG_EXTENSIONS = {
    "json", "yaml", "yml", "toml", "ini", "cfg", "conf", "xml",
    "lock", "env", "properties",
}
_DOCS_EXTENSIONS = {"md", "markdown", "rst", "txt", "adoc"}


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _extension(path: str) -> str:
    name = _basename(path)
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _categorize(path: str) -> str:
    name = _basename(path).lower()
    ext = _extension(path)
    if (
        name in _INFRA_NAMES
        or name.startswith("docker-compose")
        or name.endswith(".dockerfile")
        or ext in _INFRA_EXTENSIONS
    ):
        return "infra"
    if name in _CONFIG_NAMES or ext in _CONFIG_EXTENSIONS:
        return "config"
    if ext in _DOCS_EXTENSIONS:
        return "docs"
    return "code"


def _target_chars() -> int:
    return settings.chunk_target_tokens * settings.chunk_chars_per_token


def _overlap_chars() -> int:
    return settings.chunk_overlap_tokens * settings.chunk_chars_per_token


def _generic_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=_target_chars(), chunk_overlap=_overlap_chars()
    )


def _language_splitter(language: Language) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter.from_language(
        language=language, chunk_size=_target_chars(), chunk_overlap=_overlap_chars()
    )


def _to_language(value: object) -> Language | None:
    # LanguageParser reports the language as a Language enum when constructed
    # with one, but as a plain string under auto-detection. Some AST-supported
    # languages (e.g. sql) have no matching Language enum member for the
    # heuristic splitter, so this can legitimately return None.
    if isinstance(value, Language):
        return value
    if isinstance(value, str):
        try:
            return Language(value)
        except ValueError:
            return None
    return None


def _chunk_generic(file: RepoFile, category: str) -> Iterator[Chunk]:
    content = file["content"]
    if len(content) <= _target_chars():
        yield Chunk(
            path=file["path"], content=content, category=category,
            language=None, chunk_type="text",
        )
        return
    for piece in _generic_splitter().split_text(content):
        yield Chunk(
            path=file["path"], content=piece, category=category,
            language=None, chunk_type="text",
        )


def _chunk_tier2(file: RepoFile, category: str, language: Language) -> Iterator[Chunk]:
    content = file["content"]
    if len(content) <= _target_chars():
        yield Chunk(
            path=file["path"], content=content, category=category,
            language=language.value, chunk_type="text",
        )
        return
    for piece in _language_splitter(language).split_text(content):
        yield Chunk(
            path=file["path"], content=piece, category=category,
            language=language.value, chunk_type="text",
        )


def _chunk_tier1(file: RepoFile, category: str) -> Iterator[Chunk]:
    blob = Blob.from_data(file["content"], path=file["path"])
    try:
        docs = list(LanguageParser().lazy_parse(blob))
    except Exception:
        # Malformed source the parser can't handle: don't lose the file,
        # just fall back to plain character splitting.
        yield from _chunk_generic(file, category)
        return

    emitted = False
    for doc in docs:
        if doc.metadata.get("content_type") != "functions_classes":
            continue  # skip the 'simplified_code' file-skeleton chunk
        emitted = True
        content = doc.page_content
        raw_language = doc.metadata.get("language")
        language = _to_language(raw_language)
        lang_value = language.value if language else (
            raw_language if isinstance(raw_language, str) else None
        )

        if len(content) <= _target_chars():
            yield Chunk(
                path=file["path"], content=content, category=category,
                language=lang_value, chunk_type="function_class",
            )
            continue

        # Oversized function/class: sub-split, staying language-aware when we can.
        splitter = (
            _language_splitter(language) if language else _generic_splitter()
        )
        for piece in splitter.split_text(content):
            yield Chunk(
                path=file["path"], content=piece, category=category,
                language=lang_value, chunk_type="function_class",
            )

    if not emitted:
        # No top-level functions/classes (e.g. a flat script): chunk raw content.
        yield from _chunk_generic(file, category)


def chunk_repo_files(files: Iterable[RepoFile]) -> Iterator[Chunk]:
    """
    Splits repo files into embedding-ready chunks, routing each file to the
    most structure-aware splitter available for its language and tagging
    every chunk with a coarse category for later retrieval filtering.
    """
    for file in files:
        if not file["content"].strip():
            continue
        category = _categorize(file["path"])
        ext = _extension(file["path"])
        if ext in _TIER1_EXTENSIONS:
            yield from _chunk_tier1(file, category)
        elif ext in _TIER2_EXT_TO_LANGUAGE:
            yield from _chunk_tier2(file, category, _TIER2_EXT_TO_LANGUAGE[ext])
        else:
            yield from _chunk_generic(file, category)
