# Changelog

## Unreleased

- Add group watches for multi-process experiments, with drag-and-drop membership and editable names.
- Preserve independently expanded GPU dream cards across polling, navigation, and page reloads.
- Keep the current sidebar destination as the only selected item after data refreshes.
- Retain GPU cards during loading and ignore outdated snapshot responses.
- Refresh the root Windows executable and remove outdated design acceptance notes.
- Exclude local credentials, logs, databases, and alternate executable copies from Git.

## 0.1.0 - 2026-09-12

- Initial MVP: local and SSH detached execution.
- SQLite persistence and explicit experiment state transitions.
- CLI commands for submission, inspection, logs, waiting, cancellation, and daemon reconciliation.
- Pluggable completion wake backends for local files and commands.
- Minimal localhost dashboard and connector documentation.
