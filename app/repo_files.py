import io
import zipfile
from collections.abc import Iterator
from typing import TypedDict

from app.config import settings
from app.github_client import fetch_repo_archive

_BLOCKED_DIR_NAMES = {
    "node_modules", "vendor", "dist", "build", "target", "__pycache__",
    ".venv", "venv", ".idea", ".vscode", "bin", "obj", "coverage",
    ".next", ".pytest_cache",
}

class RepoFile(TypedDict):
    path: str
    content: str
    size: int


def _is_blocked_path(path: str) -> bool:
    parts = path.split("/")
    return any(part in _BLOCKED_DIR_NAMES for part in parts)


def _strip_archive_prefix(path: str) -> str:
    # GitHub zipballs wrap everything in a single "{owner}-{repo}-{sha}/" directory.
    _, _, rest = path.partition("/")
    return rest


def extract_repo_files(archive_bytes: bytes) -> Iterator[RepoFile]:
    """
    Parses a GitHub repo zipball entirely in memory (no disk writes) and
    yields one RepoFile per surviving file after filtering out
    non-source directories, oversized files, and binaries.
    """
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue

            path = _strip_archive_prefix(info.filename)
            if not path or _is_blocked_path(path):
                continue

            if info.file_size > settings.github_max_file_size_bytes:
                continue

            raw_bytes = archive.read(info)
            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                continue

            yield RepoFile(path=path, content=content, size=info.file_size)


async def fetch_repo_files(
    owner: str,
    repo: str,
    access_token: str | None = None,
    ref: str | None = None,
) -> Iterator[RepoFile]:
    """
    Downloads a repo's archive and extracts its filtered file contents.
    This is the function later pipeline stages (chunking) call directly.
    """
    archive_bytes = await fetch_repo_archive(owner, repo, access_token, ref)
    return extract_repo_files(archive_bytes)
