VENV_BIN := .venv/bin

default: help
.PHONY: help create-env install install-app reinstall-app upgrade format lint test check ci-status doctor connect connect-headless debug dry-run

help: # Show help for each Makefile recipe
	@grep -E '^[a-zA-Z0-9 -]+:.*#' Makefile | sort | while read -r line; do printf "\033[1;32m$$(echo $$line | cut -f 1 -d':')\033[00m:$$(echo $$line | cut -f 2- -d'#')\n"; done

create-env: # Install Python 3.14 and create a fresh uv virtual environment
	uv python install 3.14
	uv venv

install: # Install locked dependencies, Chromium, and pre-commit hooks
	uv sync --locked --group dev
	uv run playwright install chromium
	$(VENV_BIN)/pre-commit install

install-app: # Install the Citrix Launcher app under the user Applications folder
	./scripts/install_macos_app.sh

reinstall-app: # Safely replace the existing Citrix Launcher app
	./scripts/install_macos_app.sh --replace

upgrade: # Refresh the lockfile to newest allowed versions, then sync
	uv lock --upgrade
	uv sync --locked --group dev

format: # Format Python source and tests with Ruff
	$(VENV_BIN)/ruff format .

lint: # Run all pre-commit hooks (Ruff and Pyright)
	$(VENV_BIN)/pre-commit run --all-files

test: # Run unit tests
	$(VENV_BIN)/pytest -vv tests/

check: lint test # Run the complete local quality suite

ci-status: # Show CI check status for the last pushed commit on the current branch
	@sha=$$(git rev-parse HEAD); \
	branch=$$(git branch --show-current); \
	echo "Branch: $$branch"; \
	echo "Commit: $$sha ($$(git log -1 --format=%s $$sha))"; \
	ok=0; \
	for i in 1 2 3; do \
		if output=$$(gh api repos/{owner}/{repo}/commits/$$sha/check-runs --jq '.check_runs[] | [(.conclusion // .status), .name] | @tsv' 2>/dev/null); then \
			ok=1; break; \
		fi; \
		sleep 2; \
	done; \
	if [ "$$ok" -ne 1 ]; then \
		echo "Could not fetch CI checks for $$sha (not on GitHub yet? try again in a few seconds)"; \
		exit 1; \
	fi; \
	if [ -z "$$output" ]; then \
		echo "No CI checks found for this commit yet"; \
		exit 1; \
	fi; \
	echo "$$output" \
		| sort -k2 \
		| awk -F'\t' '{status=$$1; name=$$2; icon = (status == "success") ? "\033[1;32m\xe2\x9c\x93\033[00m" : "\033[1;31m\xe2\x9c\x97\033[00m"; printf "%s %-10s %s\n", icon, status, name; if (status != "success") failed=1} END {exit failed}'

doctor: # Verify configuration and required macOS components
	uv run citrix doctor

connect: # Launch the Citrix connection flow in a visible browser
	uv run citrix connect

connect-headless: # Launch using the persistent profile without a browser window
	uv run citrix connect --headless

debug: # Launch visibly with detailed safe diagnostic output
	uv run citrix connect --debug

dry-run: # Validate and print configuration without connecting
	uv run citrix connect --dry-run
