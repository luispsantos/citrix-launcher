from pathlib import Path

import pytest

from citrix_launcher.config import load_config
from citrix_launcher.errors import ConfigurationError


def test_cli_arguments_override_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CITRIX_LAUNCHER_URL", "https://environment.example.com")
    monkeypatch.setenv("CITRIX_LAUNCHER_EMAIL", "environment@example.com")
    monkeypatch.setenv("CITRIX_LAUNCHER_DESKTOP", "Environment Desktop")
    monkeypatch.setenv("CITRIX_LAUNCHER_PROFILE_DIR", str(tmp_path / "env-profile"))

    config = load_config(
        url="https://cli.example.com/login",
        email="cli@example.com",
        desktop="CLI Desktop",
        profile_dir=tmp_path / "cli-profile",
        cache_dir=tmp_path / "cache",
    )

    assert config.url == "https://cli.example.com/login"
    assert config.email == "cli@example.com"
    assert config.desktop == "CLI Desktop"
    assert config.profile_dir == tmp_path / "cli-profile"


def test_dotenv_values_are_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CITRIX_LAUNCHER_URL", raising=False)
    monkeypatch.delenv("CITRIX_LAUNCHER_EMAIL", raising=False)
    monkeypatch.delenv("CITRIX_LAUNCHER_DESKTOP", raising=False)
    (tmp_path / ".env").write_text(
        "CITRIX_LAUNCHER_URL=https://dotenv.example.com/login\n"
        "CITRIX_LAUNCHER_EMAIL=dotenv@example.com\n"
        "CITRIX_LAUNCHER_DESKTOP=Dotenv Desktop\n",
        encoding="utf-8",
    )

    config = load_config(
        profile_dir=tmp_path / "profile",
        cache_dir=tmp_path / "cache",
    )

    assert config.url == "https://dotenv.example.com/login"
    assert config.email == "dotenv@example.com"
    assert config.desktop == "Dotenv Desktop"


def test_environment_overrides_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CITRIX_LAUNCHER_URL", "https://shell.example.com")
    monkeypatch.setenv("CITRIX_LAUNCHER_EMAIL", "shell@example.com")
    monkeypatch.setenv("CITRIX_LAUNCHER_DESKTOP", "Shell Desktop")
    (tmp_path / ".env").write_text(
        "CITRIX_LAUNCHER_URL=https://dotenv.example.com\n"
        "CITRIX_LAUNCHER_EMAIL=dotenv@example.com\n"
        "CITRIX_LAUNCHER_DESKTOP=Dotenv Desktop\n",
        encoding="utf-8",
    )

    config = load_config(
        profile_dir=tmp_path / "profile",
        cache_dir=tmp_path / "cache",
    )

    assert config.url == "https://shell.example.com"
    assert config.email == "shell@example.com"
    assert config.desktop == "Shell Desktop"


def test_missing_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CITRIX_LAUNCHER_URL", raising=False)
    with pytest.raises(ConfigurationError, match="URL is required"):
        load_config(
            email="person@example.com",
            desktop="Desktop",
            cache_dir=tmp_path / "cache",
        )


def test_missing_email_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CITRIX_LAUNCHER_EMAIL", raising=False)
    with pytest.raises(ConfigurationError, match="Email is required"):
        load_config(
            url="https://example.com",
            desktop="Desktop",
            cache_dir=tmp_path / "cache",
        )


def test_missing_desktop_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CITRIX_LAUNCHER_DESKTOP", raising=False)
    with pytest.raises(ConfigurationError, match="desktop is required"):
        load_config(
            url="https://example.com",
            email="person@example.com",
            cache_dir=tmp_path / "cache",
        )


@pytest.mark.parametrize("email", ["no-at-sign", "@example.com", "a@example", "a@.com"])
def test_invalid_email_is_rejected(email: str, tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="does not appear"):
        load_config(
            url="https://example.com",
            email=email,
            desktop="Desktop",
            profile_dir=tmp_path / "profile",
            cache_dir=tmp_path / "cache",
        )


def test_cache_directory_is_created(tmp_path: Path) -> None:
    cache_dir = tmp_path / "nested" / "cache"
    config = load_config(
        url="https://example.com",
        email="person@example.com",
        desktop="Desktop",
        profile_dir=tmp_path / "profile",
        cache_dir=cache_dir,
    )
    assert config.cache_dir == cache_dir
    assert cache_dir.is_dir()
