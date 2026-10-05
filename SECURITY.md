# Security

Version 0.1.1 is experimental. Synthetic behavior tests are not a security certification or proof of production readiness.

## Trust boundaries

- The CLI records an executor's account of acceptance. It does not authenticate the person, session, or consent behind that account. A digest identifies document content; it is not a digital signature or authorization token.
- Checks can reject inconsistent CLI operations, but users and other tools can edit files directly. These records are not a tamper-proof audit log.
- The module map, plans, affected scope, and notes are supplied by users or agents. Path validation and fingerprints do not establish correct architecture, complete requirements, or exhaustive test and impact coverage.
- Markdown bodies are stored as text; the CLI does not execute commands found in them. `verify` is different: it executes `node` with the supplied Kit directory's `bin/acceptance.mjs` entrypoint. Use only a Kit you trust. That process has the invoking user's permissions and is not sandboxed by this CLI; its own code may read or write files or use the network.
- `verify` checks an existing report with the supplied Kit. It does not run tests or independently attest that the tests were appropriate. `status` displays historical verification without invoking the Kit again.

## Local data and safe use

Project paths tracked by the CLI must stay within the project root; symlinks, hardlinked files, and special files such as FIFOs are rejected. These checks do not protect against concurrent filesystem replacement by a process with the same permissions. They limit supported CLI paths, not what a separately supplied executable can access. Input JSON and note files are read from the locations supplied by the caller and must be regular files.

Records retain input text, decisions, contracts, plans, and check results. Generated index links are relative; caller-supplied text, check results, and diagnostics can still include machine-specific paths or private content. There is no automatic anonymization or secret-redaction guarantee. Review both `docs/module-change/` and `.handoff/module-change/` before publishing them; avoid entering credentials or private data into notes.

Keep both directories in backups. Exclude generated `.handoff/module-change/` records from Acceptance Kit inputs, while retaining the source and relevant documentation in acceptance coverage. Complete changes before running acceptance, and recheck evidence before relying on a previous result.

An interrupted writer may leave a lock. Inspect the recorded process and actual project state before removing it; deleting a lock while another writer is active can invalidate coordination.

## Reporting a vulnerability

Use the repository host's private vulnerability reporting channel when available. If no private contact is listed, open an issue requesting one without publishing exploit details, credentials, or private project records. Include a minimal synthetic reproduction, affected version, and expected versus observed behavior when a private channel is established.
