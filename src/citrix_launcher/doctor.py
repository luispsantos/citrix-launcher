"""Local installation checks that do not contact the Citrix portal."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from citrix_launcher.config import load_config
from citrix_launcher.errors import ConfigurationError

APP_DIR_ENV = "CITRIX_LAUNCHER_APP_DIR"
APP_NAME = "Citrix Launcher.app"
CITRIX_WORKSPACE_PATHS = (
    Path("/Applications/Citrix Workspace.app"),
    Path.home() / "Applications" / "Citrix Workspace.app",
)


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """One actionable local health check."""

    name: str
    passed: bool
    detail: str


def check_configuration() -> DoctorCheck:
    """Validate required values and writable runtime directories."""
    try:
        load_config()
    except ConfigurationError as exc:
        return DoctorCheck("Configuration", False, str(exc))
    return DoctorCheck(
        "Configuration",
        True,
        "required values and runtime directories are valid",
    )


def check_playwright_chromium() -> DoctorCheck:
    """Verify that Playwright's managed Chromium executable is installed."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return DoctorCheck("Playwright Chromium", False, str(exc))
    if result.returncode != 0:
        return DoctorCheck(
            "Playwright Chromium",
            False,
            "could not query the Playwright browser installation",
        )
    install_location = next(
        (
            Path(line.partition(":")[2].strip())
            for line in result.stdout.splitlines()
            if line.strip().startswith("Install location:")
        ),
        None,
    )
    if install_location is None or not install_location.is_dir():
        return DoctorCheck(
            "Playwright Chromium",
            False,
            "not installed; run 'uv run playwright install chromium'",
        )
    return DoctorCheck("Playwright Chromium", True, str(install_location))


def _read_plist(path: Path) -> dict[str, object] | None:
    try:
        with path.open("rb") as file:
            value = plistlib.load(file)
    except OSError, plistlib.InvalidFileException:
        return None
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def check_citrix_workspace() -> DoctorCheck:
    """Verify a standard Citrix Workspace application bundle."""
    for path in CITRIX_WORKSPACE_PATHS:
        plist = _read_plist(path / "Contents" / "Info.plist")
        bundle_id = plist.get("CFBundleIdentifier") if plist else None
        if (
            path.is_dir()
            and isinstance(bundle_id, str)
            and "citrix" in bundle_id.lower()
        ):
            return DoctorCheck("Citrix Workspace", True, str(path))
    return DoctorCheck(
        "Citrix Workspace",
        False,
        "not found in /Applications or ~/Applications",
    )


def installed_app_path() -> Path:
    """Return the app path shared with the shell installer."""
    parent = Path(os.getenv(APP_DIR_ENV, Path.home() / "Applications")).expanduser()
    return parent / APP_NAME


def check_installed_app() -> DoctorCheck:
    """Verify launcher bundle structure, icon metadata, and code signature."""
    path = installed_app_path()
    if not path.is_dir():
        return DoctorCheck(
            "Citrix Launcher app",
            False,
            f"not found at {path}; run 'make install-app'",
        )

    contents = path / "Contents"
    executable = contents / "MacOS" / "applet"
    icon = contents / "Resources" / "CitrixLauncher.icns"
    plist = _read_plist(contents / "Info.plist")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return DoctorCheck(
            "Citrix Launcher app",
            False,
            "bundle executable is missing; run 'make reinstall-app'",
        )
    if (
        plist is None
        or plist.get("CFBundleIconFile") != icon.name
        or not icon.is_file()
    ):
        return DoctorCheck(
            "Citrix Launcher app",
            False,
            "bundle icon is incomplete; run 'make reinstall-app'",
        )
    try:
        signature = subprocess.run(  # noqa: S603
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(path)],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        return DoctorCheck("Citrix Launcher app", False, str(exc))
    if signature.returncode != 0:
        return DoctorCheck(
            "Citrix Launcher app",
            False,
            "bundle signature is invalid; run 'make reinstall-app'",
        )
    return DoctorCheck("Citrix Launcher app", True, str(path))


def run_doctor() -> tuple[DoctorCheck, ...]:
    """Run every independent local health check."""
    return (
        check_configuration(),
        check_playwright_chromium(),
        check_citrix_workspace(),
        check_installed_app(),
    )
