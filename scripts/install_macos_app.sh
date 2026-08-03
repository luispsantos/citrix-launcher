#!/bin/sh
set -eu

replace=false
case ${1-} in
    "") ;;
    --replace) replace=true ;;
    *)
        echo "Usage: $0 [--replace]" >&2
        exit 2
        ;;
esac

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_parent=${CITRIX_LAUNCHER_APP_DIR:-"$HOME/Applications"}
app_path="$app_parent/Citrix Launcher.app"
icon_path="$project_dir/assets/CitrixLauncher.icns"

if [ ! -x "$project_dir/.venv/bin/citrix" ]; then
    echo "Citrix CLI is not installed. Run 'make install' first." >&2
    exit 1
fi

terminal=${CITRIX_LAUNCHER_TERMINAL:-}
if [ -z "$terminal" ] && [ -f "$project_dir/.env" ]; then
    terminal=$(
        "$project_dir/.venv/bin/python" -c \
            'import sys; from dotenv import dotenv_values; value = dotenv_values(sys.argv[1]).get("CITRIX_LAUNCHER_TERMINAL"); print(value or "")' \
            "$project_dir/.env"
    )
fi
case ${terminal:-terminal} in
    terminal | Terminal) terminal=terminal ;;
    iterm | iTerm | iterm2 | iTerm2) terminal=iterm2 ;;
    *)
        echo "Unsupported terminal: $terminal" >&2
        echo "Use CITRIX_LAUNCHER_TERMINAL=terminal or iterm2." >&2
        exit 1
        ;;
esac

if [ "$terminal" = iterm2 ] && \
    [ ! -d "/Applications/iTerm.app" ] && \
    [ ! -d "$HOME/Applications/iTerm.app" ]; then
    echo "iTerm2 is not installed in /Applications or ~/Applications." >&2
    exit 1
fi

had_existing=false
if [ -e "$app_path" ]; then
    had_existing=true
    if [ "$replace" = false ]; then
        echo "Application already exists: $app_path" >&2
        echo "Run 'make reinstall-app' to replace it safely." >&2
        exit 1
    fi
fi

if [ ! -f "$icon_path" ]; then
    echo "Application icon is missing: $icon_path" >&2
    exit 1
fi

mkdir -p "$app_parent"

staging_dir=$(mktemp -d "$app_parent/.citrix-launcher-install.XXXXXX")
staged_app="$staging_dir/Citrix Launcher.app"
backup_dir=
swap_complete=false

cleanup() {
    status=$?
    trap - EXIT HUP INT TERM

    if [ "$status" -ne 0 ] && [ "$swap_complete" = false ] && [ -n "$backup_dir" ]; then
        backup_app="$backup_dir/Citrix Launcher.app"
        if [ -e "$backup_app" ] && [ ! -e "$app_path" ]; then
            mv "$backup_app" "$app_path" || true
        fi
    fi

    rm -rf "$staging_dir"
    if [ -n "$backup_dir" ]; then
        backup_app="$backup_dir/Citrix Launcher.app"
        if [ "$status" -eq 0 ] || [ "$swap_complete" = true ]; then
            rm -rf "$backup_dir"
        elif [ ! -e "$backup_app" ]; then
            rmdir "$backup_dir" 2>/dev/null || true
        fi
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

# Escape the checkout path for an AppleScript string literal. The generated app
# deliberately contains only this local path; URL/email remain in the ignored .env.
escaped_project_dir=$(printf '%s' "$project_dir" | sed 's/\\/\\\\/g; s/"/\\"/g')

if [ "$terminal" = iterm2 ]; then
    osacompile -o "$staged_app" \
        -e 'property launcherTab : missing value' \
        -e 'property stateDirectory : missing value' \
        -e 'property cancelRequested : false' \
        -e 'on run' \
        -e 'set my cancelRequested to false' \
        -e "set projectDirectory to \"$escaped_project_dir\"" \
        -e 'set runCommand to "echo \"Starting Citrix Launcher...\"; cd " & quoted form of projectDirectory & " && .venv/bin/citrix connect --headless"' \
        -e 'set my stateDirectory to do shell script "mktemp -d /tmp/citrix-launcher.XXXXXX"' \
        -e 'set completionMarker to my stateDirectory & "/complete"' \
        -e 'set guardedCommand to runCommand & "; status=$?; if [ \"$status\" -ne 0 ]; then echo; echo \"Citrix Launcher failed. Press Return to close.\"; read ignored; fi; touch " & quoted form of completionMarker & "; exit \"$status\""' \
        -e 'set shellCommand to "exec /bin/sh -c " & quoted form of guardedCommand' \
        -e 'tell application "iTerm2"' \
        -e 'activate' \
        -e 'if (count of windows) is 0 then' \
        -e 'set launcherWindow to (create window with default profile)' \
        -e 'set my launcherTab to current tab of launcherWindow' \
        -e 'else' \
        -e 'set launcherWindow to current window' \
        -e 'tell launcherWindow to set my launcherTab to (create tab with default profile)' \
        -e 'end if' \
        -e 'select my launcherTab' \
        -e 'set launcherSession to current session of my launcherTab' \
        -e 'repeat 50 times' \
        -e 'try' \
        -e 'if is at shell prompt of launcherSession then exit repeat' \
        -e 'end try' \
        -e 'delay 0.1' \
        -e 'end repeat' \
        -e 'tell launcherSession to write text shellCommand' \
        -e 'end tell' \
        -e 'repeat' \
        -e 'if my cancelRequested then exit repeat' \
        -e 'try' \
        -e 'do shell script "test -f " & quoted form of completionMarker' \
        -e 'exit repeat' \
        -e 'on error' \
        -e 'try' \
        -e 'tell application "iTerm2" to set tabExists to exists my launcherTab' \
        -e 'if not tabExists then exit repeat' \
        -e 'on error' \
        -e 'exit repeat' \
        -e 'end try' \
        -e 'end try' \
        -e 'delay 0.2' \
        -e 'end repeat' \
        -e 'try' \
        -e 'tell application "iTerm2" to close my launcherTab' \
        -e 'end try' \
        -e 'do shell script "rm -rf " & quoted form of my stateDirectory' \
        -e 'set my launcherTab to missing value' \
        -e 'set my stateDirectory to missing value' \
        -e 'end run' \
        -e 'on quit' \
        -e 'set my cancelRequested to true' \
        -e 'try' \
        -e 'tell application "iTerm2" to close my launcherTab' \
        -e 'end try' \
        -e 'try' \
        -e 'if my stateDirectory is not missing value then do shell script "rm -rf " & quoted form of my stateDirectory' \
        -e 'end try' \
        -e 'continue quit' \
        -e 'end quit'
else
    osacompile -o "$staged_app" \
        -e 'on run' \
        -e "set projectDirectory to \"$escaped_project_dir\"" \
        -e 'set runCommand to "echo \"Starting Citrix Launcher...\"; cd " & quoted form of projectDirectory & " && .venv/bin/citrix connect --headless"' \
        -e 'set guardedCommand to runCommand & "; status=$?; if [ \"$status\" -ne 0 ]; then echo; echo \"Citrix Launcher failed. Press Return to close.\"; read ignored; fi; exit \"$status\""' \
        -e 'set shellCommand to "exec /bin/sh -c " & quoted form of guardedCommand' \
        -e 'tell application "Terminal"' \
        -e 'activate' \
        -e 'do script shellCommand' \
        -e 'set launcherWindow to front window' \
        -e 'repeat while busy of selected tab of launcherWindow' \
        -e 'delay 0.2' \
        -e 'end repeat' \
        -e 'close launcherWindow' \
        -e 'end tell' \
        -e 'end run'
fi

cp "$icon_path" "$staged_app/Contents/Resources/CitrixLauncher.icns"
/usr/libexec/PlistBuddy \
    -c 'Set :CFBundleIconFile CitrixLauncher.icns' \
    "$staged_app/Contents/Info.plist"
/usr/libexec/PlistBuddy \
    -c 'Delete :CFBundleIconName' \
    "$staged_app/Contents/Info.plist" >/dev/null 2>&1 || true
codesign --force --deep --sign - "$staged_app" >/dev/null
codesign --verify --deep --strict "$staged_app"
touch "$staged_app"

if [ "$had_existing" = true ]; then
    backup_dir=$(mktemp -d "$app_parent/.citrix-launcher-backup.XXXXXX")
    mv "$app_path" "$backup_dir/Citrix Launcher.app"
fi
mv "$staged_app" "$app_path"
swap_complete=true

if [ "$had_existing" = true ]; then
    echo "Reinstalled for $terminal: $app_path"
else
    echo "Installed for $terminal: $app_path"
fi
echo "Launch it from Finder, Spotlight, or the Applications folder."
