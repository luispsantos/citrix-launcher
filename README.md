# citrix-launcher

`citrix-launcher` is a small macOS command-line tool that drives a configured
Citrix login interface in an isolated Playwright browser profile, pauses for a
manually entered PingID code, downloads the resulting ICA file, and asks Citrix
Workspace to open it.

The installed command is `citrix`; its initial workflow is `citrix connect`.

This is an independent, unofficial project. It is not affiliated with or endorsed
by Citrix. Citrix and Citrix Workspace are trademarks of their respective owners.

## Security boundaries

This project automates visible browser actions only. It does not generate,
intercept, approve, store, or bypass MFA. The PingID code is requested with hidden
terminal input only after the portal displays its OTP field, then retained only
long enough to fill that field. The tool does not extract tokens, replay sessions,
disable certificate checks, inspect ICA contents, or use the normal Chrome
profile.

The dedicated Playwright profile does retain browser session data. Protect it as
authentication material. `--diagnostics` is off by default because screenshots,
page URLs, and traces can contain sensitive deployment information.

Use this workflow only with a Citrix environment you are authorized to access and
automate.

## Prerequisites

- macOS
- [Citrix Workspace](https://www.citrix.com/downloads/workspace-app/mac/) installed
- Python 3.14
- [uv](https://docs.astral.sh/uv/)

## Setup

```console
make install
uv run citrix --help
```

`make install` performs the locked dependency sync, installs Playwright Chromium,
and installs the Git pre-commit hooks. Run `make help` to list all available local
workflows. The equivalent individual commands are `uv sync --locked --group dev`,
`uv run playwright install chromium`, and `uv run pre-commit install`.

### macOS application launcher

Install a lightweight personal app after the normal setup:

```console
make install-app
```

This creates `~/Applications/Citrix Launcher.app`. Opening it from Finder,
Spotlight, or Launchpad starts the existing CLI in Terminal, where PingID remains
hidden manual input when required. The app uses headless browser automation and
closes only the terminal window it created when the flow finishes. If the flow
fails, the window waits for Return so the error remains visible. The generated app
uses the project's custom icon and stores only the absolute path to this checkout;
URL, email, desktop, and terminal configuration stay in the ignored `.env`, and
the sensitive browser profile remains under macOS Application Support.

Terminal.app is the default. To use iTerm2, add this to `.env` before installing
or reinstalling the app:

```dotenv
CITRIX_LAUNCHER_TERMINAL=iterm2
```

The supported values are `terminal` and `iterm2`. With iTerm2, the launcher opens
and selects a dedicated tab in the current window so the OTP prompt remains
visible, then closes only that tab. The selected terminal is embedded in the
generated app, so run `make reinstall-app` after changing it. Dock **Quit** closes
the launcher tab and cancels the flow.

The installer refuses to overwrite an existing app. After changing the launcher,
icon, or repository location, safely refresh the app with:

```console
make reinstall-app
```

The replacement is built and signature-checked before the existing app is moved.
If the final swap fails, the installer restores the previous app.

The Chromium installation downloads a Playwright-managed browser. It does not use
or modify the user's ordinary Chrome profile.

## Configuration and use

The URL, email, desktop name, and profile directory can be supplied as options:

```console
uv run citrix connect \
  --url https://citrix.example.com/login \
  --email person@example.com \
  --desktop "My Desktop" \
  --profile-dir "$HOME/Library/Application Support/citrix-launcher/browser-profile"
```

The browser is headed by default. `--headless` is available but authentication or
client detection may behave differently. `--diagnostics` opts into failure
screenshots, the current URL, and a Playwright trace under the application cache;
treat those files as sensitive.

Use `--debug` to print chained exceptions and safe step/download metadata directly
in the terminal while diagnosing automation. Debug output never intentionally
includes OTP values, cookies, tokens, page HTML, or browser storage. It may include
local profile/cache paths and downloaded filenames. `--diagnostics` is separate and
more sensitive because it writes screenshots and traces.

Equivalent environment variables are:

- `CITRIX_LAUNCHER_URL`
- `CITRIX_LAUNCHER_EMAIL`
- `CITRIX_LAUNCHER_DESKTOP`
- `CITRIX_LAUNCHER_PROFILE_DIR`
- `CITRIX_LAUNCHER_TERMINAL` (used when installing the macOS app)

Command-line options take precedence. Credentials and OTP values are never
configuration values.

For local configuration, copy the provided example and edit the three required
values:

```console
cp .env.example .env
```

The `.env` file is ignored by Git and is loaded from the current working
directory. Precedence is command-line options, existing shell or direnv variables,
then `.env`. Store only the portal URL, email, desktop name, optional dedicated
profile path, and app-terminal preference there—never passwords, OTP values,
cookies, tokens, or other authentication material.

Check resolved configuration without opening a browser, requesting an OTP, or
launching Citrix Workspace:

```console
uv run citrix connect --dry-run
```

Verify the complete local setup without contacting the portal:

```console
make doctor
```

This checks configuration, Playwright Chromium, Citrix Workspace, and the
installed Citrix Launcher app bundle and signature.

By default, the isolated browser profile is under
`~/Library/Application Support/citrix-launcher/` and ICA files are cached under
`~/Library/Caches/citrix-launcher/`. At the beginning of a real connection, regular
ICA files older than one day are removed. A newly opened ICA file is deliberately
kept because Citrix Workspace may still be reading it.

The profile persists the authorized browser session. On later runs, the launcher
recognizes the current portal stage. When StoreFront already displays the configured
desktop, it skips email, PingID, and Workspace detection and launches directly. If
the session has expired, it resumes from whichever login stage is shown and prompts
for an OTP only when the PingID field is actually visible.
Redirect pages may briefly contain multiple portal markers; state recognition
filters for visible controls and tolerates those transitional duplicates.

## Portal compatibility and selectors

The portal controls are centralized in `PortalSelectors` in
`src/citrix_launcher/browser.py`. Citrix deployments can differ, so the included
selectors may need to be adapted to the visible controls in your authorized
environment. The configured flow uses stable element IDs for the email and PingID
controls and accessible roles for actionable links and buttons.

The OTP is entered with Playwright keyboard events rather than bulk value filling
because PingID uses those events to enable its submit control.
Terminal input must be exactly six ASCII digits; malformed input is rejected
locally and does not consume a PingID attempt.
Enter `quit`, `exit`, or `q` at the hidden OTP prompt to cancel cleanly.
If PingID visibly rejects a code, the launcher clears the field and prompts again.
After three rejected codes it exits so a fresh connection can be started.

The observed `Detect Citrix Workspace app` control is clicked automatically after
authentication. If Citrix shows its detection fallback page, the launcher selects
`Already installed`; it does not accept the download license or download another
copy of Workspace. The actionable link is selected by role because the same words
also appear as non-interactive explanatory text on that page. Chromium may instead
show an external-application confirmation
the first time; approve opening Citrix Workspace manually and allow it permanently
only when authorized. The dedicated persistent browser profile can
retain that choice for later runs. These clicks do not wait for conventional page
navigation because Citrix combines browser navigation with a native-app protocol.

On the StoreFront home page, the desktop named by `CITRIX_LAUNCHER_DESKTOP` (or
`--desktop`) is clicked and its ICA download is captured directly into the launcher
cache. The file is validated using metadata only and opened with
`/Applications/Citrix Workspace.app`; its contents are never inspected. StoreFront
may supply a UUID filename without an extension, so the launcher adds `.ica` to
that expected desktop-download event.
Downloads carrying a different extension are rejected. The desktop click does not
wait for page navigation; its Playwright download event is the authoritative
completion signal. StoreFront renders the desktop name twice inside one tile, so
the launcher targets the unique surrounding link rather than either duplicate
text node.

Prefer accessible labels, placeholders, and button roles over long CSS selectors
or XPath. The browser uses Playwright waits rather than fixed sleeps.

## Development

```console
make format
make lint
make test
make check
make ci-status
make doctor
```

`make ci-status` requires the GitHub CLI (`gh`) to be authenticated and reports the
checks for the current local commit. It fails clearly when the commit has not been
pushed or checks have not appeared yet.

Pre-commit runs Gitleaks against staged changes before each commit. GitHub Actions
also scans the complete Git history so secrets introduced outside the local hook
are caught before changes are accepted.

Never commit browser profile data, traces, ICA files, screenshots, cookies,
credentials, OTP values, or other authentication material. These runtime files
belong only in the macOS application-support and cache directories, never in this
repository.

## License

This project is available under the [MIT License](LICENSE).
