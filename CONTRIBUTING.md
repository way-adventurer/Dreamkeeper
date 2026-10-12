# Contributing

1. Create a focused branch from the default branch.
2. Keep changes small and explain behavior changes in the changelog.
3. Run python -m pytest before opening a pull request.
4. Do not add credentials, private SSH keys, experiment logs, or model transcripts to the repository.
5. New executor and wake implementations should have unit tests and an explicit security note.

Dashboard state regression tests run in a headless browser with synthetic servers and GPU snapshots; they do not connect to configured SSH hosts. With Node.js, Playwright, and Microsoft Edge installed, run `node --test tests/ui/dashboard_state.cjs`. Set `TEST_BROWSER=chrome` to use Google Chrome instead, and `PYTHON` to override the Python executable (the project virtual environment is used by default).

