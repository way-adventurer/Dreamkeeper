# Changelog

## 0.2.2 - 2026-11-03

- Remove cancelled group cards, member monitor records, and their logs when cancelling a group; allow deleting older cancelled groups.

## 0.2.1 - 2026-11-03

- Let users cancel a running group watch without stopping remote processes or sending a completion notice.

## 0.2.0 - 2026-11-03

- Reopen the dashboard on every Windows launcher click, including when it is already running.
- Wait for the local HTTP service before opening the browser on a cold start.
- Add the glass dock, command search, card lighting, dark surface hierarchy, and refined motion.
- Ship one canonical `Dreamkeeper.exe` name for the Windows build and one-click copy.
- Distinguish unreadable SSH config paths from missing files and allow local file selection for import.
- Make whole process cards draggable, expose naming and group assignment controls, refine the glass dock and routing contrast, and auto-dismiss operation messages.
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
