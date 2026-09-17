# RunRelay operating instructions

When an experiment is expected to run for more than a short interactive command:

1. Submit it to RunRelay with the exact host, work directory, and command.
2. Record the returned experiment ID.
3. Prefer runrelay wait <id> for a single blocking handoff, or submit and return when a separate monitor is already running.
4. Do not repeatedly poll with ps, tail, or nvidia-smi from the agent loop.
5. After completion, inspect status, logs, exit code, and artifacts before making the next research decision.

Never enable automated Codex wake-up without reviewing the continuation prompt and session ID.

