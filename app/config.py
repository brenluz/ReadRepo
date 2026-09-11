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

    class Config:
        env_file = ".env"


settings = Settings()