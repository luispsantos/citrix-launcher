"""Playwright workflow with portal-specific selectors kept in one place."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, sync_playwright

from citrix_launcher.config import AppConfig
from citrix_launcher.errors import (
    DownloadError,
    PortalAutomationError,
    UserCancelledError,
)

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext

logger = logging.getLogger(__name__)
MAX_OTP_ATTEMPTS = 3
MAX_PORTAL_STEPS = 9
OTP_RESULT_SCRIPT = """
({ selector }) => {
    const field = document.querySelector(selector);
    if (!field) return true;
    const style = window.getComputedStyle(field);
    const hidden = style.display === "none" ||
        style.visibility === "hidden" || field.getClientRects().length === 0;
    if (hidden) return true;
    const pageText = (document.body?.innerText || "").toLowerCase();
    const rejectionText = [
        "invalid", "incorrect", "expired", "try again",
        "authentication failed", "not accepted"
    ];
    return field.getAttribute("aria-invalid") === "true" ||
        rejectionText.some((message) => pageText.includes(message));
}
"""


@dataclass(frozen=True, slots=True)
class LocatorSpec:
    """A resilient accessible locator description."""

    kind: str
    value: str


class PortalState(StrEnum):
    """Recognizable stages of the persisted portal session."""

    EMAIL = "email sign-in"
    OTP = "PingID"
    WORKSPACE_DETECT = "Workspace detection"
    ALREADY_INSTALLED = "Workspace detection fallback"
    DESKTOP = "StoreFront desktop"


@dataclass(frozen=True, slots=True)
class PortalSelectors:
    """All portal-specific labels.

    These selectors reflect the observed PingID and StoreFront pages.
    """

    launch: LocatorSpec
    email: LocatorSpec = LocatorSpec("css", "#username")
    email_submit: LocatorSpec = LocatorSpec("css", "#postsubmitbutton")
    otp: LocatorSpec = LocatorSpec("css", "#otp")
    otp_submit: LocatorSpec = LocatorSpec("role_button", "Sign On")
    workspace_detect: LocatorSpec = LocatorSpec("text", "Detect Citrix Workspace app")
    workspace_already_installed: LocatorSpec = LocatorSpec(
        "role_link", "Already installed"
    )


def _locator(page: Page, spec: LocatorSpec) -> Locator:
    if spec.kind == "css":
        return page.locator(spec.value)
    if spec.kind == "label":
        return page.get_by_label(spec.value, exact=False)
    if spec.kind == "placeholder":
        return page.get_by_placeholder(spec.value, exact=False)
    if spec.kind == "role_button":
        return page.get_by_role("button", name=spec.value, exact=False)
    if spec.kind == "role_link":
        return page.get_by_role("link", name=spec.value, exact=True)
    if spec.kind == "link_text":
        return page.locator("a").filter(has_text=spec.value)
    if spec.kind == "text":
        return page.get_by_text(spec.value, exact=True)
    raise PortalAutomationError(f"Unsupported portal locator kind: {spec.kind}")


def _prompt_for_otp() -> str:
    """Prompt until the user enters exactly six ASCII digits."""
    while True:
        otp = typer.prompt("PingID code (or 'quit')", hide_input=True).strip()
        if otp.casefold() in {"q", "quit", "exit"}:
            raise UserCancelledError("Connection cancelled.")
        if len(otp) == 6 and otp.isascii() and otp.isdigit():
            return otp
        typer.echo("PingID code must be exactly 6 digits (0-9).", err=True)


def ica_destination(cache_dir: Path, suggested_filename: str) -> Path:
    """Choose a safe ICA path for a StoreFront desktop download."""
    name = Path(suggested_filename).name
    suffix = Path(name).suffix.lower()
    if suffix and suffix != ".ica":
        raise DownloadError(f"Portal download is not an ICA file: {name}")
    if not suffix:
        # This StoreFront returns a UUID filename without the ICA suffix. The file
        # is trusted only as the direct download event from the configured desktop.
        name = f"{name}.ica"
    return cache_dir / name


class PortalBrowser:
    """Run ordinary UI actions in an isolated persistent Chromium profile."""

    def __init__(
        self, config: AppConfig, selectors: PortalSelectors | None = None
    ) -> None:
        self.config = config
        self.selectors = selectors or PortalSelectors(
            launch=LocatorSpec("link_text", config.desktop)
        )

    def connect(self) -> Path:
        with sync_playwright() as playwright:
            context: BrowserContext | None = None
            page: Page | None = None
            try:
                logger.debug(
                    "Opening persistent Chromium profile at %s", self.config.profile_dir
                )
                context = playwright.chromium.launch_persistent_context(
                    str(self.config.profile_dir),
                    headless=not self.config.headed,
                    accept_downloads=True,
                )
                if self.config.diagnostics:
                    context.tracing.start(screenshots=True, snapshots=True)
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(self.config.timeout_ms)
                return self._complete_portal_flow(page)
            except PlaywrightError as exc:
                if page is not None:
                    self._save_failure_diagnostics(page)
                raise PortalAutomationError(
                    "An unhandled Playwright operation failed; rerun with --debug "
                    "for the underlying operation."
                ) from exc
            finally:
                if context is not None:
                    if self.config.diagnostics:
                        trace_path = self._diagnostics_dir() / "trace.zip"
                        try:
                            context.tracing.stop(path=trace_path)
                        except PlaywrightError:
                            logger.warning("Could not save the Playwright trace.")
                    context.close()

    def _complete_portal_flow(self, page: Page) -> Path:
        logger.debug("Navigating to configured Citrix URL.")
        page.goto(self.config.url, wait_until="domcontentloaded")
        otp_attempts = 0
        for _ in range(MAX_PORTAL_STEPS):
            state = self._wait_for_portal_state(page)
            logger.info("Portal state: %s.", state.value)
            if state is PortalState.DESKTOP:
                return self._download_ica(page)
            if state is PortalState.EMAIL:
                self._submit_email(page)
            elif state is PortalState.OTP:
                if not self._submit_otp(page):
                    otp_attempts += 1
                    if otp_attempts >= MAX_OTP_ATTEMPTS:
                        raise PortalAutomationError(
                            "PingID rejected three codes; start the connection again."
                        )
                    logger.warning("PingID code was not accepted. Try again.")
                else:
                    otp_attempts = 0
            elif state is PortalState.WORKSPACE_DETECT:
                self._start_workspace_detection(page)
            elif state is PortalState.ALREADY_INSTALLED:
                self._confirm_workspace_installed(page)
        raise PortalAutomationError("Portal did not reach the StoreFront desktop.")

    def _wait_for_portal_state(self, page: Page) -> PortalState:
        locators = {
            PortalState.EMAIL: _locator(page, self.selectors.email),
            PortalState.OTP: _locator(page, self.selectors.otp),
            PortalState.WORKSPACE_DETECT: _locator(
                page, self.selectors.workspace_detect
            ),
            PortalState.ALREADY_INSTALLED: _locator(
                page, self.selectors.workspace_already_installed
            ),
            PortalState.DESKTOP: _locator(page, self.selectors.launch),
        }
        visible_stage = locators[PortalState.EMAIL]
        for locator in tuple(locators.values())[1:]:
            visible_stage = visible_stage.or_(locator)
        try:
            # The portal may temporarily retain more than one matching element
            # during SAML redirects. Filter first so Locator strictness does not
            # turn a valid visible stage into an automation failure.
            visible_stage.filter(visible=True).first.wait_for(state="visible")
        except PlaywrightError as exc:
            raise PortalAutomationError(
                "Could not recognize the current Citrix portal screen."
            ) from exc
        for state in (
            PortalState.DESKTOP,
            PortalState.ALREADY_INSTALLED,
            PortalState.WORKSPACE_DETECT,
            PortalState.OTP,
            PortalState.EMAIL,
        ):
            if locators[state].is_visible():
                return state
        raise PortalAutomationError(
            "Could not recognize the current Citrix portal screen."
        )

    def _submit_email(self, page: Page) -> None:
        try:
            _locator(page, self.selectors.email).fill(self.config.email)
            _locator(page, self.selectors.email_submit).click()
        except PlaywrightError as exc:
            raise PortalAutomationError(
                "Email sign-in step failed. Expected the observed PingIdentity "
                "controls '#username' and '#postsubmitbutton'."
            ) from exc

    def _submit_otp(self, page: Page) -> bool:
        """Submit one OTP and report whether PingID advanced past its input."""
        try:
            otp_field = _locator(page, self.selectors.otp)
            otp_field.wait_for(state="visible")
        except PlaywrightError as exc:
            raise PortalAutomationError(
                "The email was submitted, but the PingID field could not be found. "
                "Expected the observed '#otp' control."
            ) from exc
        otp = _prompt_for_otp()
        # The OTP exists only in this local variable and is never logged or persisted.
        try:
            # PingID enables its submit control from keyboard events; fill() changes
            # the value in bulk and leaves the real page's button disabled. Clear any
            # rejected value first, then type the replacement as keyboard events.
            otp_field.fill("")
            otp_field.press_sequentially(otp)
            _locator(page, self.selectors.otp_submit).click(no_wait_after=True)
            page.wait_for_function(
                OTP_RESULT_SCRIPT,
                arg={"selector": self.selectors.otp.value},
            )
        except PlaywrightError as exc:
            raise PortalAutomationError(
                "PingID did not report whether the code was accepted. "
                "Start the connection again."
            ) from exc
        return not otp_field.is_visible()

    def _start_workspace_detection(self, page: Page) -> None:
        try:
            detect = _locator(page, self.selectors.workspace_detect)
            # Citrix starts a custom-protocol/navigation transition. Do not make
            # Playwright wait for it as though it were an ordinary page load.
            detect.click(no_wait_after=True)
            detect.wait_for(state="hidden")
        except PlaywrightError as exc:
            raise PortalAutomationError(
                "Could not activate 'Detect Citrix Workspace app'."
            ) from exc

    def _confirm_workspace_installed(self, page: Page) -> None:
        try:
            already_installed = _locator(
                page, self.selectors.workspace_already_installed
            )
            already_installed.click(no_wait_after=True)
            already_installed.wait_for(state="hidden")
        except PlaywrightError as exc:
            raise PortalAutomationError(
                "Could not activate the 'Already installed' Workspace link."
            ) from exc

    def _download_ica(self, page: Page) -> Path:
        try:
            launch = _locator(page, self.selectors.launch)
            launch.wait_for(state="visible")
            with page.expect_download(timeout=self.config.timeout_ms) as download_info:
                # StoreFront starts a download alongside its own transition logic.
                # The download event, not a conventional navigation, is completion.
                launch.click(no_wait_after=True)
            download = download_info.value
        except PlaywrightError as exc:
            raise PortalAutomationError(
                f"The StoreFront portal opened, but the {self.config.desktop!r} "
                "desktop tile did not produce an ICA download."
            ) from exc
        destination = ica_destination(
            self.config.cache_dir, download.suggested_filename
        )
        logger.debug(
            "StoreFront suggested download name: %s", download.suggested_filename
        )
        try:
            download.save_as(destination)
        except PlaywrightError as exc:
            raise DownloadError(
                f"Could not save the ICA download to the cache: {destination.name}"
            ) from exc
        logger.info("Saved ICA download as %s.", destination.name)
        return destination

    def _diagnostics_dir(self) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = self.config.cache_dir / "diagnostics" / stamp
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _save_failure_diagnostics(self, page: Page) -> None:
        if not self.config.diagnostics:
            return
        directory = self._diagnostics_dir()
        try:
            page.screenshot(path=directory / "failure.png")
            (directory / "url.txt").write_text(page.url, encoding="utf-8")
            logger.warning("Sensitive diagnostics saved under %s", directory)
        except OSError, PlaywrightError:
            logger.warning("Could not save browser failure diagnostics.")
