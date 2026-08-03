from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from playwright.sync_api import Page

from citrix_launcher.browser import (
    LocatorSpec,
    PortalBrowser,
    PortalSelectors,
    PortalState,
    ica_destination,
)
from citrix_launcher.config import AppConfig
from citrix_launcher.errors import (
    DownloadError,
    PortalAutomationError,
    UserCancelledError,
)


class _TestablePortalBrowser(PortalBrowser):
    def complete_for_test(self, page: Page) -> Path:
        return self._complete_portal_flow(page)

    def submit_otp_for_test(self, page: Page) -> bool:
        return self._submit_otp(page)


def test_portal_email_and_otp_selectors_are_configured() -> None:
    selectors = PortalSelectors(launch=LocatorSpec("link_text", "Test Desktop"))

    assert selectors.email.kind == "css"
    assert selectors.email.value == "#username"
    assert selectors.email_submit.kind == "css"
    assert selectors.email_submit.value == "#postsubmitbutton"
    assert selectors.otp.kind == "css"
    assert selectors.otp.value == "#otp"
    assert selectors.otp_submit.kind == "role_button"
    assert selectors.otp_submit.value == "Sign On"
    assert selectors.workspace_detect.kind == "text"
    assert selectors.workspace_detect.value == "Detect Citrix Workspace app"
    assert selectors.workspace_already_installed.kind == "role_link"
    assert selectors.workspace_already_installed.value == "Already installed"
    assert selectors.launch.kind == "link_text"
    assert selectors.launch.value == "Test Desktop"


def test_extensionless_storefront_download_gets_ica_suffix(tmp_path: Path) -> None:
    destination = ica_destination(tmp_path, "desktop-download-id")

    assert destination == tmp_path / "desktop-download-id.ica"


def test_download_with_foreign_extension_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DownloadError, match="not an ICA"):
        ica_destination(tmp_path, "unexpected.zip")


def test_authenticated_profile_skips_otp_prompt(tmp_path: Path) -> None:
    config = AppConfig(
        url="https://citrix.example.com",
        email="person@example.com",
        desktop="Test Desktop",
        profile_dir=tmp_path / "profile",
        cache_dir=tmp_path / "cache",
    )
    browser = _TestablePortalBrowser(config)
    page_mock = MagicMock(spec=Page)
    page = cast(Page, page_mock)
    expected = tmp_path / "desktop.ica"

    with (
        patch.object(
            browser,
            "_wait_for_portal_state",
            return_value=PortalState.DESKTOP,
        ),
        patch.object(browser, "_download_ica", return_value=expected),
        patch("citrix_launcher.browser.typer.prompt") as prompt,
    ):
        result = browser.complete_for_test(page)

    assert result == expected
    prompt.assert_not_called()


def test_rejected_otp_is_retried_before_desktop(tmp_path: Path) -> None:
    config = AppConfig(
        url="https://citrix.example.com",
        email="person@example.com",
        desktop="Test Desktop",
        profile_dir=tmp_path / "profile",
        cache_dir=tmp_path / "cache",
    )
    browser = _TestablePortalBrowser(config)
    page = cast(Page, MagicMock(spec=Page))
    expected = tmp_path / "desktop.ica"

    with (
        patch.object(
            browser,
            "_wait_for_portal_state",
            side_effect=[PortalState.OTP, PortalState.OTP, PortalState.DESKTOP],
        ),
        patch.object(browser, "_submit_otp", side_effect=[False, True]) as submit,
        patch.object(browser, "_download_ica", return_value=expected),
    ):
        result = browser.complete_for_test(page)

    assert result == expected
    assert submit.call_count == 2


def test_three_rejected_otp_codes_stop_the_flow(tmp_path: Path) -> None:
    config = AppConfig(
        url="https://citrix.example.com",
        email="person@example.com",
        desktop="Test Desktop",
        profile_dir=tmp_path / "profile",
        cache_dir=tmp_path / "cache",
    )
    browser = _TestablePortalBrowser(config)
    page = cast(Page, MagicMock(spec=Page))

    with (
        patch.object(
            browser,
            "_wait_for_portal_state",
            return_value=PortalState.OTP,
        ),
        patch.object(browser, "_submit_otp", return_value=False) as submit,
        pytest.raises(PortalAutomationError, match="rejected three codes"),
    ):
        browser.complete_for_test(page)

    assert submit.call_count == 3


def test_otp_submission_clears_rejected_value_and_detects_retry(
    tmp_path: Path,
) -> None:
    config = AppConfig(
        url="https://citrix.example.com",
        email="person@example.com",
        desktop="Test Desktop",
        profile_dir=tmp_path / "profile",
        cache_dir=tmp_path / "cache",
    )
    browser = _TestablePortalBrowser(config)
    page_mock = MagicMock(spec=Page)
    page = cast(Page, page_mock)
    otp_field = MagicMock()
    otp_field.is_visible.return_value = True
    submit = MagicMock()

    with (
        patch(
            "citrix_launcher.browser._locator",
            side_effect=[otp_field, submit],
        ),
        patch(
            "citrix_launcher.browser.typer.prompt",
            side_effect=[
                "12",
                "12345a",
                "\uff11\uff12\uff13\uff14\uff15\uff16",
                "123456",
            ],
        ) as prompt,
        patch("citrix_launcher.browser.typer.echo") as echo,
    ):
        accepted = browser.submit_otp_for_test(page)

    assert not accepted
    otp_field.fill.assert_called_once_with("")
    otp_field.press_sequentially.assert_called_once_with("123456")
    submit.click.assert_called_once_with(no_wait_after=True)
    page_mock.wait_for_function.assert_called_once()
    assert prompt.call_count == 4
    assert echo.call_count == 3
    echo.assert_called_with(
        "PingID code must be exactly 6 digits (0-9).",
        err=True,
    )


def test_otp_prompt_can_cancel_without_submitting(tmp_path: Path) -> None:
    config = AppConfig(
        url="https://citrix.example.com",
        email="person@example.com",
        desktop="Test Desktop",
        profile_dir=tmp_path / "profile",
        cache_dir=tmp_path / "cache",
    )
    browser = _TestablePortalBrowser(config)
    page = cast(Page, MagicMock(spec=Page))
    otp_field = MagicMock()

    with (
        patch("citrix_launcher.browser._locator", return_value=otp_field),
        patch("citrix_launcher.browser.typer.prompt", return_value="quit"),
        pytest.raises(UserCancelledError, match="cancelled"),
    ):
        browser.submit_otp_for_test(page)

    otp_field.press_sequentially.assert_not_called()
