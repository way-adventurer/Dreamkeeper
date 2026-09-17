# Codex integration capability audit

Audited on 2026-09-12 against the official OpenAI/Codex documentation and the installed local CLI (codex-cli 0.154.0-alpha.6.2). This document intentionally separates what is verified from what is still an assumption.

## VERIFIED

- Official Codex non-interactive mode documents codex exec for scripts and CI.
- codex exec --json emits a JSONL event stream, including thread, turn, item, and error events.
- The installed CLI exposes codex exec resume [SESSION_ID] [PROMPT] and codex resume [SESSION_ID] [PROMPT].
- The official Codex SDK documentation exposes resumeThread(threadId) in TypeScript.
- The official App Server protocol documents thread/resume for a stored thread.
- Codex hooks exist, but they are lifecycle hooks, not a general “start a new model turn after an arbitrary external event” API.

## PARTIALLY VERIFIED

- RunRelay can start a local `codex exec resume` process after an experiment completes. The plugin adapter captures `CODEX_THREAD_ID`/`CODEX_SESSION_ID` when available, so the user does not need to copy the thread ID manually.
- The Python SDK controls the local Codex App Server, but RunRelay does not bundle or require that optional dependency in the MVP.
- The exact persistence and cross-client behavior of a thread depends on the local Codex runtime, configuration, and session source.

## UNVERIFIED

- Directly waking an already-open Codex Desktop conversation from an arbitrary external process without starting a Codex CLI/SDK/App Server client.
- Interoperability of every Desktop session with every CLI/SDK resume path.
- Host-side timeout limits for a multi-hour blocking tool call in every Codex Desktop and CLI environment.

## MVP decision

RunRelay implements an `auto` wake backend for the Codex MCP adapter. It resumes a persisted local Codex CLI thread when the host provides a thread/session ID, and falls back to noop when it does not. It does not claim to inject a new message into an arbitrary open Desktop or SSH remote-project conversation. File and command remain useful for notification or custom integrations.

Official references:

- https://learn.chatgpt.com/docs/codex-sdk
- https://learn.chatgpt.com/docs/app-server
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/hooks
