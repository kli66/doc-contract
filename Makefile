.PHONY: bump test check build clean help

## bump   — bump the VCS version from conventional commits, update CHANGELOG, and create a tag
bump:
	uv run --group lint cz bump --changelog

## test   — run the complete test suite
test:
	uv run --group test pytest -q

## check  — run lint and the offline resolver gate
check:
	uv run --group lint ruff check .
	uv run doc-contract check --repo-root . --offline

## build  — build the wheel using the version resolved from Git tags
build:
	uv build --wheel

## clean  — remove package build artifacts
clean:
	rm -rf build dist src/*.egg-info

.DEFAULT_GOAL := help
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## //'
