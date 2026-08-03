# Repository Guidelines

## Project Shape

- Python 3.14 package under `src/citrix_launcher`; the Typer entrypoint is
  `citrix_launcher.cli:app`, installed as `citrix`.
- Keep the project small: configuration is in `config.py`, portal automation in
  `browser.py`, expected errors in `errors.py`, and macOS ICA handling in
  `launcher.py`.
- Runtime browser data and downloads must remain outside the repository. The
  defaults are `~/Library/Application Support/citrix-launcher/browser-profile`
  and `~/Library/Caches/citrix-launcher`.
- `make install-app` creates `~/Applications/Citrix Launcher.app` as a thin
  Terminal wrapper around this checkout and embeds `assets/CitrixLauncher.icns`.
  `make reinstall-app` builds and verifies a replacement before swapping it with
  the existing bundle. The wrapper runs `citrix connect --headless`, supports
  Terminal.app or iTerm2 through `CITRIX_LAUNCHER_TERMINAL`, and closes only its
  own window or tab after completion. The iTerm2 wrapper must keep the OTP tab
  visible and handle Dock Quit without leaving the CLI running. Keep
  authentication logic in the Python CLI rather than duplicating it in AppleScript.
- Never use, inspect, or modify the user's ordinary Chrome profile.

## Setup and Checks

- Sync the locked environment with `uv sync --locked`.
- Install Playwright Chromium with `uv run playwright install chromium`.
- Preferred repository commands are `make install`, `make format`, `make lint`,
  `make test`, `make check`, and `make doctor`; use `make help` for the full list.
- `make doctor` performs local read-only checks for configuration, Playwright
  Chromium, Citrix Workspace, and the installed launcher app. It must never
  contact the portal or inspect authentication data.
- `make ci-status` reports GitHub checks for the current commit and requires an
  authenticated GitHub CLI.
- Run `make check` before handing off a code change. Run `make lint` when preparing
  a commit or changing repository configuration.
- Keep `uv.lock` tracked and update it whenever dependencies change.
- GitHub Actions mirrors these checks in separate lint and unit-test jobs on
  Ubuntu with Python 3.14. A separate Gitleaks job scans complete Git history, and
  the pre-commit hook scans staged changes. CI intentionally does not install a
  browser or access the real portal.

## Security Boundaries

- OTP entry is always manual and terminal-only. Never automate, generate,
  intercept, approve, log, persist, screenshot, replay, or include OTP values in
  exceptions, tests, fixtures, or shell commands.
- Do not extract cookies, authentication tokens, browser storage, sensitive page
  HTML, credentials, or private authentication APIs. Do not bypass MFA,
  certificate validation, or automation controls.
- Treat the persistent browser profile, screenshots, traces, ICA files, cookies,
  and authentication material as sensitive. Never place or copy them into the
  repository.
- Do not inspect or parse ICA contents. Validation is limited to the path suffix,
  existence, regular-file status, and non-zero size.
- `.env` may contain only the portal URL, email, desktop name, optional dedicated
  profile path, and app-terminal preference. Never place passwords, OTPs, cookies,
  or tokens there. `.env` and `.envrc` must remain ignored.
- Keep Gitleaks enabled. Any false-positive exclusion must be narrowly scoped and
  documented; never suppress an entire sensitive file type or broad path.

## Portal Automation

- `PortalBrowser` is a state-aware workflow. A persisted session may start at the
  email page, PingID, Workspace detection, its `Already installed` fallback, or
  the StoreFront desktop. Do not restore a rigid always-login sequence.
- Prompt for PingID only after the `#otp` field is visible. Use
  `press_sequentially` because PingID enables submission from keyboard events;
  bulk `fill()` leaves its button disabled. Accept exactly six ASCII digits and
  reject malformed terminal input locally. A visibly rejected code may be retried
  manually up to three times; clear the field first and never log an attempted
  value. `q`, `quit`, and `exit` cancel locally without submitting a value.
- Keep portal-specific locators centralized in `PortalSelectors`. Prefer stable
  accessible roles or element IDs. StoreFront may render the configured desktop
  name twice inside one tile, so target its unique surrounding link rather than
  either text node. The desktop name comes from `CITRIX_LAUNCHER_DESKTOP` or
  `--desktop`; do not hardcode it in browser automation.
- Citrix detection and desktop launch clicks use non-navigation behavior because
  StoreFront combines custom-protocol logic, browser transitions, and downloads.
  Use visible-state or download-event waits; do not add arbitrary sleeps.
- The desktop download event is the authoritative completion signal. StoreFront
  may suggest a UUID filename without a suffix; add `.ica` only for an
  extensionless download captured directly from the configured desktop event.
  Reject downloads carrying another extension.
- Real portal selectors should be learned only from authorized visible UI or
  narrowly scoped DOM inspection. Do not save full page HTML or sensitive browser
  state.

## Diagnostics and Testing

- `citrix connect --debug` prints chained exceptions and safe automation metadata.
  Keep debug output free of OTPs, cookies, tokens, page HTML, and browser storage.
- `--diagnostics` is opt-in and more sensitive because it saves screenshots, the
  current URL, and Playwright traces under the application cache. Never enable it
  automatically.
- Unit tests must not access a live portal. Test state transitions,
  selector configuration, download-path rules, configuration precedence, cleanup,
  and subprocess construction with mocks or local fixtures.
- Expected application errors should remain concise without tracebacks unless the
  user explicitly enables `--debug`.

## macOS ICA Launching

- macOS launching uses `open -a "Citrix Workspace" <ica-path>` through
  `subprocess.run()` without `shell=True`.
- Validate the ICA file before invoking Citrix Workspace. Do not delete it
  immediately afterward because Workspace may still be reading it.
- Cleanup must stay narrowly scoped to expired regular `.ica` files directly in
  the application cache; never follow symlinks or recursively delete broad paths.
