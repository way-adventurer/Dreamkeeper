# Security

Dreamkeeper executes commands supplied by the user. Treat submitted commands, remote paths, and logs as sensitive.

- SSH is delegated to the system ssh client and the user's SSH configuration.
- Passwords and private keys are not accepted or persisted.
- The dashboard binds to 127.0.0.1 by default.
- The local database may contain commands, paths, and wake configuration; protect the Dreamkeeper state directory.
- Logs may contain secrets emitted by an experiment. Do not publish the state directory.
- Command wake-up can execute a local shell command with experiment metadata in environment variables. Review the command before enabling it.

Please report security issues privately to the repository maintainers rather than opening a public issue with exploit details.
