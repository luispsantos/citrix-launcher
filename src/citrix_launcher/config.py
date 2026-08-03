"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from citrix_launcher.errors import ConfigurationError

URL_ENV = "CITRIX_LAUNCHER_URL"
EMAIL_ENV = "CITRIX_LAUNCHER_EMAIL"
DESKTOP_ENV = "CITRIX_LAUNCHER_DESKTOP"
PROFILE_DIR_ENV = "CITRIX_LAUNCHER_PROFILE_DIR"


def default_profile_dir() -> Path:
    """Return the dedicated browser profile path (never the normal Chrome profile)."""
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "citrix-launcher"
        / "browser-profile"
    )


def default_cache_dir() -> Path:
    """Return the macOS application cache path."""
    return Path.home() / "Library" / "Caches" / "citrix-launcher"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated runtime configuration."""

    url: str
    email: str
    desktop: str
    profile_dir: Path
    cache_dir: Path
    headed: bool = True
    diagnostics: bool = False
    debug: bool = False
    timeout_ms: int = 30_000
    retention_seconds: int = 86_400


def _validate_url(value: str | None) -> str:
    if value is None or not value.strip():
        raise ConfigurationError(f"Citrix URL is required (--url or {URL_ENV}).")
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError("Citrix URL must be a valid http:// or https:// URL.")
    return url


def _validate_email(value: str | None) -> str:
    if value is None or not value.strip():
        raise ConfigurationError(f"Email is required (--email or {EMAIL_ENV}).")
    email = value.strip()
    local, separator, domain = email.rpartition("@")
    if (
        not separator
        or not local
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
    ):
        raise ConfigurationError("Email address does not appear to be valid.")
    return email


def _validate_desktop(value: str | None) -> str:
    if value is None or not value.strip():
        raise ConfigurationError(
            f"Citrix desktop is required (--desktop or {DESKTOP_ENV})."
        )
    return value.strip()


def _ensure_directory(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    try:
        expanded.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(
            f"Cannot create {label} directory: {expanded}"
        ) from exc
    if not expanded.is_dir():
        raise ConfigurationError(
            f"{label.capitalize()} path is not a directory: {expanded}"
        )
    return expanded


def load_config(
    *,
    url: str | None = None,
    email: str | None = None,
    desktop: str | None = None,
    profile_dir: Path | None = None,
    cache_dir: Path | None = None,
    headed: bool = True,
    diagnostics: bool = False,
    debug: bool = False,
) -> AppConfig:
    """Load CLI-over-environment-over-.env configuration and create directories."""
    # Existing shell/direnv values win because .env never overrides the environment.
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    resolved_url = url if url is not None else os.getenv(URL_ENV)
    resolved_email = email if email is not None else os.getenv(EMAIL_ENV)
    resolved_desktop = desktop if desktop is not None else os.getenv(DESKTOP_ENV)
    env_profile = os.getenv(PROFILE_DIR_ENV)
    resolved_profile = profile_dir or (
        Path(env_profile) if env_profile else default_profile_dir()
    )
    resolved_cache = cache_dir or default_cache_dir()

    return AppConfig(
        url=_validate_url(resolved_url),
        email=_validate_email(resolved_email),
        desktop=_validate_desktop(resolved_desktop),
        profile_dir=_ensure_directory(resolved_profile, "profile"),
        cache_dir=_ensure_directory(resolved_cache, "cache"),
        headed=headed,
        diagnostics=diagnostics,
        debug=debug,
    )
