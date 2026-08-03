from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from citrix_launcher.cli import app
from citrix_launcher.doctor import DoctorCheck
from citrix_launcher.errors import UserCancelledError

runner = CliRunner()


def test_dry_run_does_not_open_browser_or_launch_citrix(tmp_path: Path) -> None:
    with (
        patch("citrix_launcher.cli.PortalBrowser") as browser,
        patch("citrix_launcher.cli.launch_ica") as launch,
    ):
        result = runner.invoke(
            app,
            [
                "connect",
                "--url",
                "https://citrix.example.com",
                "--email",
                "person@example.com",
                "--desktop",
                "Test Desktop",
                "--profile-dir",
                str(tmp_path / "profile"),
                "--dry-run",
            ],
            env={"HOME": str(tmp_path)},
        )

    assert result.exit_code == 0
    assert "Dry run: configuration is valid" in result.stdout
    assert "https://citrix.example.com" in result.stdout
    assert "person@example.com" in result.stdout
    assert "Test Desktop" in result.stdout
    browser.assert_not_called()
    launch.assert_not_called()


def test_doctor_reports_success() -> None:
    checks = (DoctorCheck("Configuration", True, "valid"),)
    with patch("citrix_launcher.cli.run_doctor", return_value=checks):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "✓ Configuration: valid" in result.stdout
    assert "Doctor found no problems." in result.stdout


def test_doctor_exits_nonzero_when_a_check_fails() -> None:
    checks = (DoctorCheck("Citrix Workspace", False, "not found"),)
    with patch("citrix_launcher.cli.run_doctor", return_value=checks):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "✗ Citrix Workspace: not found" in result.stdout
    assert "Doctor found 1 problem(s)." in result.stderr


def test_connect_treats_user_cancellation_as_success(tmp_path: Path) -> None:
    with patch(
        "citrix_launcher.cli.PortalBrowser.connect",
        side_effect=UserCancelledError("Connection cancelled."),
    ):
        result = runner.invoke(
            app,
            [
                "connect",
                "--url",
                "https://citrix.example.com",
                "--email",
                "person@example.com",
                "--desktop",
                "Test Desktop",
                "--profile-dir",
                str(tmp_path / "profile"),
            ],
            env={"HOME": str(tmp_path)},
        )

    assert result.exit_code == 0
    assert "Connection cancelled." in result.stdout
