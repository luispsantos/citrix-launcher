"""Safe validation, cleanup, and macOS launching of ICA files."""

from __future__ import annotations

import logging
import platform
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from citrix_launcher.errors import CitrixLaunchError, DownloadError

logger = logging.getLogger(__name__)


def validate_ica_file(path: Path) -> None:
    """Validate only file metadata; ICA contents are intentionally never inspected."""
    if path.suffix.lower() != ".ica":
        raise DownloadError(f"Downloaded file is not an ICA file: {path.name}")
    if not path.is_file():
        raise DownloadError(f"ICA file does not exist: {path}")
    if path.stat().st_size == 0:
        raise DownloadError(f"ICA file is empty: {path}")


def build_open_command(path: Path) -> list[str]:
    """Build the macOS command without invoking a shell."""
    return ["open", "-a", "Citrix Workspace", str(path)]


def launch_ica(path: Path) -> None:
    """Ask macOS to open a validated ICA file with Citrix Workspace."""
    validate_ica_file(path)
    if platform.system() != "Darwin":
        raise CitrixLaunchError(
            "Citrix Workspace launching is supported only on macOS."
        )
    logger.debug("Opening validated ICA file with Citrix Workspace: %s", path.name)
    try:
        # The validated path is one argv item; no shell interpretation occurs.
        subprocess.run(build_open_command(path), check=True)  # noqa: S603
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CitrixLaunchError(
            "Could not open the ICA file with Citrix Workspace. "
            "Confirm that Citrix Workspace is installed."
        ) from exc


def cleanup_expired_ica_files(
    cache_dir: Path,
    *,
    retention_seconds: int = 86_400,
    now: Callable[[], float] = time.time,
) -> list[Path]:
    """Delete only expired regular .ica files directly inside the app cache."""
    removed: list[Path] = []
    cutoff = now() - retention_seconds
    for path in cache_dir.glob("*.ica"):
        try:
            if (
                path.is_file()
                and not path.is_symlink()
                and path.stat().st_mtime < cutoff
            ):
                path.unlink()
                removed.append(path)
        except OSError as exc:
            logger.warning("Could not remove expired ICA file %s: %s", path.name, exc)
    return removed
