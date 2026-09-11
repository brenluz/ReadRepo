import httpx
from fastapi import APIRouter, HTTPException, Query

from app.github_client import (
    ArchiveTooLargeError,
    GithubApiError,
    RateLimitedError,
    RepoNotFoundError,
)
from app.repo_files import fetch_repo_files

router = APIRouter(prefix="/repos")


@router.get("/{owner}/{repo}/files")
async def list_repo_files(owner: str, repo: str, ref: str | None = Query(default=None)):
    # Smoke-test route for this increment: proves the fetch -> extract ->
    # filter pipeline works end to end. Returns paths only, not full file
    # contents - the future chunking step will consume fetch_repo_files
    # directly rather than going through this HTTP response.
    try:
        files = list(await fetch_repo_files(owner, repo, ref=ref))
    except RepoNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"{owner}/{repo} not found, inaccessible, or empty",
        )
    except RateLimitedError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        raise HTTPException(
            status_code=429,
            detail="GitHub API rate limit exceeded",
            headers=headers,
        )
    except ArchiveTooLargeError:
        raise HTTPException(
            status_code=413,
            detail=f"{owner}/{repo} archive exceeds the size limit",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Timed out fetching repo archive from GitHub",
        )
    except GithubApiError:
        raise HTTPException(
            status_code=502,
            detail="Unexpected error fetching repo from GitHub",
        )

    return {
        "file_count": len(files),
        "paths": [file["path"] for file in files],
    }
