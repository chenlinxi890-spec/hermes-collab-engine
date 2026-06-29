# Contributing to Hermes Collab Engine

Thanks for helping improve Hermes Collab Engine. This project coordinates AI workers, local dashboards, sandbox runs, and release documentation, so small, well-scoped contributions are easiest to review.

## Start here

1. Read the release notes in [`CHANGELOG.md`](CHANGELOG.md) and the current roadmap in [`ROADMAP.md`](ROADMAP.md).
2. Install locally:

   ```bash
   python3 -m pip install -e .
   ```

3. Run the narrow check for the area you changed. For general Python changes:

   ```bash
   PYTHONPATH=src python3 -m unittest discover -s tests -v
   ```

4. For dashboard or sandbox changes, also review [`sandbox/README.md`](sandbox/README.md) and avoid committing runtime databases or generated logs.

## Issue triage

Use the GitHub issue templates when possible:

- Bug reports should include reproduction steps, expected behavior, actual behavior, environment, and relevant logs with secrets removed.
- Feature requests should describe the user workflow, proposed behavior, alternatives considered, and safety impact.
- Documentation issues should name the affected language or page and the command or workflow that confused you.

Please keep one issue focused on one problem. Security vulnerabilities should not be filed as public issues; follow [`SECURITY.md`](SECURITY.md).


### Suggested labels for triage

- good first issue — small, well-scoped tasks for newcomers
- documentation — docs, README, guides, issue templates
- 	ests — test additions, test fixes, test infrastructure
- dashboard — dashboard UI, layout, components
- sandbox — sandbox configuration, examples, README
- security — vulnerabilities (see [SECURITY.md](SECURITY.md))
## Pull request workflow

- Open focused PRs with a clear summary, linked issue, and verification commands.
- Keep generated/runtime artifacts out of the diff, especially `data/*.sqlite3`, logs, credentials, local `.env` files, and real Hermes or Claude configuration.
- Match existing style and naming. Prefer concise Markdown, simple Python, and explicit safety boundaries.
- Update docs and localization together when user-facing behavior changes. At minimum, note whether `README.md`, `README.en.md`, and `README.ja.md` need follow-up.
- Include screenshots or API payload examples for dashboard-visible changes when practical.

## Tests and verification

Choose the smallest command that proves the change:

```bash
python3 -m py_compile src/hermes_collab_engine/*.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
bash -n scripts/start_sandbox.sh scripts/install.sh
```

If a command fails, include the failure in the PR and explain whether it is related to your change.

## Safety boundaries

Hermes Collab Engine should remain safe for public release:

- Do not commit real API keys, auth files, tokens, session data, SQLite runtime state, or private logs.
- Do not make sandbox examples call real workers by default.
- Keep dashboard exposure local-first unless a deployment guide explicitly adds authentication, network binding guidance, and risk warnings.
- Do not broaden tool permissions, git write access, or process execution without documenting the reason and review path.

