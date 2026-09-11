import time

import httpx

from app.config import settings

GITHUB_API_BASE_URL = "https://api.github.com"


class GithubApiError(Exception):
    """Base class for errors talking to the GitHub API."""


class RepoNotFoundError(GithubApiError):
    """Repo doesn't exist, isn't accessible, or is empty."""


class RateLimitedError(GithubApiError):
    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(f"GitHub API rate limit hit (retry_after={retry_after})")


class ArchiveTooLargeError(GithubApiError):
    """Archive exceeded the configured size cap before it finished downloading."""


def _rate_limit_retry_after(response: httpx.Response) -> int | None:
    retry_after = response.headers.get("retry-after")
    if retry_after is not None:
        try:
            return int(retry_after)
        except ValueError:
            return None

    reset = response.headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            return max(0, int(reset) - int(time.time()))
        except ValueError:
            return None

    return None


def _is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        return True
    return False


async def fetch_repo_archive(
    owner: str,
    repo: str,
    access_token: str | None = None,
    ref: str | None = None,
) -> bytes:
    """
    Downloads a repo's zipball into memory (never written to disk) in a
    single GitHub API request, regardless of repo size. Enforces
    settings.github_max_archive_bytes while streaming so an oversized
    archive is aborted early instead of fully buffered first.
    """
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/zipball"
    if ref:
        url = f"{url}/{ref}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.github_http_timeout_seconds,
    ) as client:
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 404:
                raise RepoNotFoundError(f"{owner}/{repo} not found, inaccessible, or empty")
            if _is_rate_limited(response):
                raise RateLimitedError(retry_after=_rate_limit_retry_after(response))
            if response.status_code != 200:
                raise GithubApiError(
                    f"Unexpected status {response.status_code} fetching {owner}/{repo} archive"
                )

            chunks: list[bytes] = []
            total_bytes = 0
            async for chunk in response.aiter_bytes():
                total_bytes += len(chunk)
                if total_bytes > settings.github_max_archive_bytes:
                    raise ArchiveTooLargeError(
                        f"{owner}/{repo} archive exceeded "
                        f"{settings.github_max_archive_bytes} byte cap"
                    )
                chunks.append(chunk)

    return b"".join(chunks)
