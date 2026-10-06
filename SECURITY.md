# Security

Version 0.2.1 is experimental. Synthetic behavior tests and small integration examples are not a security certification or proof of production readiness.

## Trust boundaries

- The CLI records an executor's account of acceptance. It does not authenticate the person, session, or consent behind it. Digests identify content, not signatures or authorization tokens. Direct file edits remain possible; this is not a tamper-proof audit log.
- Discovery inventories structure and fingerprints. Business module boundaries, relationships, contracts, and coverage are reviewed by an agent or contributor. Static evidence cannot establish correct architecture or exhaustive behavior. Files, comments, and imported tool output are untrusted material, not instructions granting more access.
- Maps and checks use a specific project root. Optional analysis tools are not installed automatically and must not silently redirect to another checkout. Scanning does not execute project code or intentionally use the network; external analysis tools have their own trust boundaries.
- Markdown is stored as text, not executed. `run-checks` executes the supplied Kit and commands in selected configurations. `verify` executes its `bin/acceptance.mjs` checker. Both run with the invoking user's permissions; this CLI supplies no operating-system sandbox. Commands may read or write files, access the network, or launch other programs. Use a trusted Kit and inspect configurations before authorizing execution.
- Declared check IDs, configurations, steps, and inputs are compared with the frozen plan. This detects protocol and scope mismatches, not semantic coverage or whether a test command is appropriate. A project-wide receipt is not automatically evidence for every module.
- `status` displays historical evidence and local fingerprint changes without running the Kit. Recheck receipts before relying on old results. `delivery_ready` is an evidence gate for configured required checks, not a project-quality or architecture guarantee.

## Local data and safe use

Project paths supported by the CLI stay within the specified root. Symlinks, hardlinked files, and special files such as FIFOs are rejected or reported as excluded by discovery; they are not followed to collect data. These checks do not prevent concurrent filesystem replacement by a process with the same permissions and do not restrict a separately supplied executable. Explicit JSON and note inputs are read from caller-supplied locations and must be regular files.

Scan exclusions and size limits reduce collection; they are not secret detection or anonymization. Even an inventory can reveal private filenames, relationships, source identifiers, or paths. Records retain maps, findings, contracts, decisions, plans, frozen configuration JSON, and check results. Generated links are relative, but caller-supplied text and Kit output or diagnostics may contain machine paths, private data, or credentials. There is no automatic redaction guarantee.

The core records remain local and are not uploaded automatically. Review both `docs/module-change/` and `.handoff/module-change/` before sharing or committing them. Configure project-specific exclusions before scanning and avoid entering secrets into notes. Optional tools and configured test commands may have separate network behavior.

Back up current documents and persistent records together. Exclude generated `.handoff/module-change/` records or `.handoff` from Kit inputs while retaining related source, configurations, tests, and documentation. Complete those changes before acceptance; recording an event must not immediately invalidate the report. The CLI does not silently rewrite Kit configuration to achieve a pass.

Map acceptance writes several files. Per-file replacement is not a cross-file transaction or a power-loss recovery mechanism. After an exception or interruption, inspect the current map, accepted candidate, archive, and lock before retrying; do not assume that all writes completed or were rolled back.

An interrupted writer may leave a lock. Inspect its process and actual project state before removing it; deleting a lock while another writer is active can invalidate coordination.

## Reporting a vulnerability

Use the repository host's private vulnerability reporting channel when available. If no private contact is listed, open an issue requesting one without publishing exploit details, credentials, or private project records. Include a minimal synthetic reproduction, affected version, and expected versus observed behavior once a private channel is established.
