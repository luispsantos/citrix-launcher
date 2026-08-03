"""Command-line interface."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from citrix_launcher.browser import PortalBrowser
from citrix_launcher.config import AppConfig, load_config
from citrix_launcher.doctor import run_doctor
from citrix_launcher.errors import CitrixLauncherError, UserCancelledError
from citrix_launcher.launcher import cleanup_expired_ica_files, launch_ica

app = typer.Typer(help="Launch a desktop through a configured Citrix portal.")
logger = logging.getLogger(__name__)


@app.callback()
def main() -> None:
    """Launch a desktop through a configured Citrix portal."""


def _print_dry_run(config: AppConfig) -> None:
    typer.echo("Dry run: configuration is valid; no browser or Citrix app was opened.")
    typer.echo(f"URL: {config.url}")
    typer.echo(f"Email: {config.email}")
    typer.echo(f"Desktop: {config.desktop}")
    typer.echo(f"Profile directory: {config.profile_dir}")
    typer.echo(f"Cache directory: {config.cache_dir}")
    typer.echo(f"Browser mode: {'headed' if config.headed else 'headless'}")


@app.command()
def doctor() -> None:
    """Check local configuration and required macOS components."""
    checks = run_doctor()
    for check in checks:
        marker = "✓" if check.passed else "✗"
        typer.echo(f"{marker} {check.name}: {check.detail}")
    failures = sum(not check.passed for check in checks)
    if failures:
        typer.echo(f"Doctor found {failures} problem(s).", err=True)
        raise typer.Exit(code=1)
    typer.echo("Doctor found no problems.")


@app.command()
def connect(
    url: Annotated[str | None, typer.Option(help="Citrix portal login URL.")] = None,
    email: Annotated[str | None, typer.Option(help="Sign-in email address.")] = None,
    desktop: Annotated[
        str | None,
        typer.Option(help="StoreFront desktop name to launch."),
    ] = None,
    headed: Annotated[
        bool,
        typer.Option("--headed/--headless", help="Show or hide the browser window."),
    ] = True,
    profile_dir: Annotated[
        Path | None,
        typer.Option(help="Dedicated Playwright profile directory."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(help="Validate and display configuration only."),
    ] = False,
    diagnostics: Annotated[
        bool,
        typer.Option(help="Save sensitive failure screenshots, URL, and a trace."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option(help="Print detailed exceptions and safe automation metadata."),
    ] = False,
) -> None:
    """Authenticate manually where required and launch the Citrix desktop."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s: %(message)s",
        force=True,
    )
    try:
        config = load_config(
            url=url,
            email=email,
            desktop=desktop,
            profile_dir=profile_dir,
            headed=headed,
            diagnostics=diagnostics,
            debug=debug,
        )
        if dry_run:
            _print_dry_run(config)
            return

        removed = cleanup_expired_ica_files(
            config.cache_dir, retention_seconds=config.retention_seconds
        )
        if removed:
            logger.info("Removed %d expired ICA file(s).", len(removed))
        ica_path = PortalBrowser(config).connect()
        logger.debug("Validated browser download path: %s", ica_path)
        launch_ica(ica_path)
        typer.echo("Citrix Workspace launch requested successfully.")
    except UserCancelledError as exc:
        typer.echo(str(exc))
    except CitrixLauncherError as exc:
        if debug:
            logger.exception("Detailed Citrix launcher failure")
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
