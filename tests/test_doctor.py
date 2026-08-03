import os
import plistlib
from pathlib import Path
from unittest.mock import Mock, patch

from citrix_launcher.doctor import (
    DoctorCheck,
    check_installed_app,
    check_playwright_chromium,
    run_doctor,
)


def _create_launcher_app(path: Path) -> None:
    executable = path / "Contents" / "MacOS" / "applet"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"executable")
    executable.chmod(0o755)
    resources = path / "Contents" / "Resources"
    resources.mkdir()
    (resources / "CitrixLauncher.icns").write_bytes(b"icon")
    with (path / "Contents" / "Info.plist").open("wb") as file:
        plistlib.dump({"CFBundleIconFile": "CitrixLauncher.icns"}, file)


def test_installed_app_check_validates_bundle_and_signature(tmp_path: Path) -> None:
    app_path = tmp_path / "Citrix Launcher.app"
    _create_launcher_app(app_path)
    signature = Mock(returncode=0)

    with (
        patch.dict(os.environ, {"CITRIX_LAUNCHER_APP_DIR": str(tmp_path)}),
        patch("citrix_launcher.doctor.subprocess.run", return_value=signature) as run,
    ):
        result = check_installed_app()

    assert result.passed
    run.assert_called_once_with(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app_path)],
        check=False,
        capture_output=True,
    )


def test_installed_app_check_reports_missing_app(tmp_path: Path) -> None:
    with patch.dict(
        os.environ, {"CITRIX_LAUNCHER_APP_DIR": str(tmp_path)}, clear=False
    ):
        result = check_installed_app()

    assert not result.passed
    assert "make install-app" in result.detail


def test_playwright_check_uses_reported_install_location(tmp_path: Path) -> None:
    chromium_dir = tmp_path / "chromium-1234"
    chromium_dir.mkdir()
    process = Mock(
        returncode=0,
        stdout=f"Chrome for Testing\n  Install location: {chromium_dir}\n",
    )

    with patch("citrix_launcher.doctor.subprocess.run", return_value=process) as run:
        result = check_playwright_chromium()

    assert result.passed
    assert result.detail == str(chromium_dir)
    run.assert_called_once()


def test_playwright_check_reports_missing_installation(tmp_path: Path) -> None:
    process = Mock(
        returncode=0,
        stdout=f"Chrome for Testing\n  Install location: {tmp_path / 'missing'}\n",
    )

    with patch("citrix_launcher.doctor.subprocess.run", return_value=process):
        result = check_playwright_chromium()

    assert not result.passed
    assert "playwright install chromium" in result.detail


def test_run_doctor_collects_every_check() -> None:
    checks = tuple(
        DoctorCheck(name, True, "ok")
        for name in ("config", "chromium", "workspace", "app")
    )
    with (
        patch("citrix_launcher.doctor.check_configuration", return_value=checks[0]),
        patch(
            "citrix_launcher.doctor.check_playwright_chromium",
            return_value=checks[1],
        ),
        patch("citrix_launcher.doctor.check_citrix_workspace", return_value=checks[2]),
        patch("citrix_launcher.doctor.check_installed_app", return_value=checks[3]),
    ):
        assert run_doctor() == checks
