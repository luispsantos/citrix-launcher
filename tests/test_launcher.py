import os
from pathlib import Path
from unittest.mock import patch

import pytest

from citrix_launcher.errors import DownloadError
from citrix_launcher.launcher import (
    build_open_command,
    cleanup_expired_ica_files,
    launch_ica,
    validate_ica_file,
)


def test_non_ica_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "launch.txt"
    path.write_text("not inspected", encoding="utf-8")
    with pytest.raises(DownloadError, match="not an ICA"):
        validate_ica_file(path)


def test_empty_ica_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.ica"
    path.touch()
    with pytest.raises(DownloadError, match="empty"):
        validate_ica_file(path)


def test_build_open_command(tmp_path: Path) -> None:
    path = tmp_path / "desktop.ica"
    assert build_open_command(path) == [
        "open",
        "-a",
        "Citrix Workspace",
        str(path),
    ]


def test_launch_ica_runs_expected_command(tmp_path: Path) -> None:
    path = tmp_path / "desktop.ica"
    path.write_bytes(b"opaque data")
    with (
        patch("citrix_launcher.launcher.platform.system", return_value="Darwin"),
        patch("citrix_launcher.launcher.subprocess.run") as run,
    ):
        launch_ica(path)
    run.assert_called_once_with(build_open_command(path), check=True)


def test_cleanup_removes_only_expired_ica_files(tmp_path: Path) -> None:
    old_ica = tmp_path / "old.ica"
    fresh_ica = tmp_path / "fresh.ica"
    old_other = tmp_path / "old.txt"
    for path in (old_ica, fresh_ica, old_other):
        path.write_bytes(b"data")
    os.utime(old_ica, (100.0, 100.0))
    os.utime(old_other, (100.0, 100.0))
    os.utime(fresh_ica, (950.0, 950.0))

    removed = cleanup_expired_ica_files(
        tmp_path, retention_seconds=100, now=lambda: 1_000.0
    )

    assert removed == [old_ica]
    assert not old_ica.exists()
    assert fresh_ica.exists()
    assert old_other.exists()
