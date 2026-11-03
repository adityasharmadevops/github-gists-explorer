"""Read and validate the small set of settings our service needs."""

from dataclasses import dataclass, field
import math
import os


@dataclass(frozen=True)
class Settings:
    """A named, immutable group of settings; tokens stay out of its repr."""

    timeout_seconds: float = 5
    request_budget_seconds: float = 20
    max_pages: int = 20
    github_token: str = field(default="", repr=False)
    log_level: str = "INFO"

    def __post_init__(self):
        for name in ("timeout_seconds", "request_budget_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive, finite number.")
        if self.max_pages <= 0:
            raise ValueError("max_pages must be a positive integer.")
        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")

    @classmethod
    def from_env(cls):
        """Use defaults unless the person running the service provides values."""
        return cls(
            timeout_seconds=float(os.getenv("GITHUB_TIMEOUT_SECONDS", "5")),
            request_budget_seconds=float(os.getenv("GITHUB_REQUEST_BUDGET_SECONDS", "20")),
            max_pages=int(os.getenv("GITHUB_MAX_PAGES", "20")),
            github_token=os.getenv("GITHUB_TOKEN", "").strip(),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
