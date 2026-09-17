# Security

Dreamkeeper executes commands supplied by the user. Treat submitted commands, remote paths, and logs as sensitive.

- SSH is delegated to the system ssh client and the user's SSH configuration.
- Passwords and private keys are not accepted or persisted.
- The dashboard binds to 127.0.0.1 by default.
- The local database may contain commands, paths, session IDs, and wake configuration; protect the Dreamkeeper state directory.
- Logs may contain secrets emitted by an experiment. Do not publish the state directory.
- codex-cli wake-up intentionally starts a new local Codex process with the supplied session ID and prompt. Review that prompt before enabling it.

Please report security issues privately to the repository maintainers rather than opening a public issue with exploit details.
