# Security

Version 0.5.0 is experimental. Synthetic behavior tests and small integration examples are not a security certification or proof of production readiness.

## Trust boundaries

- The CLI records an executor's account of acceptance. It does not authenticate the person, session, or consent behind it. Digests identify content, not signatures or authorization tokens. Direct file edits remain possible; this is not a tamper-proof audit log.
- Discovery inventories structure and fingerprints. Business module boundaries, relationships, contracts, and coverage are reviewed by an agent or contributor. Static evidence cannot establish correct architecture or exhaustive behavior. Files, comments, and imported tool output are untrusted material, not instructions granting more access.
- Maps and checks use a specific project root. A normal scan does not install optional analysis tools. Explicit enhanced installation can install CodeGraph and prepare a selected host configuration; it must not silently redirect to another checkout. Scanning does not execute project code or intentionally use the network; external analysis tools have their own trust boundaries.
- Markdown is stored as text, not executed. `run-checks` executes the selected Kit and commands in selected configurations. `verify` executes its `bin/acceptance.mjs` checker. The bundled runtime is the default; `--kit` selects an explicit external directory, and an invalid explicit path does not fall back to the bundle. Both commands require Node.js 22+ and run with the invoking user's permissions; this CLI supplies no operating-system sandbox. Commands inherit environment variables and may read or write files, access the network, or launch other programs. Shared dependency directories and absolute paths can affect the original project or files outside the input copy. Use a trusted Kit and inspect configurations before authorizing execution.
- Declared check IDs, configurations, steps, and inputs are compared with the frozen plan. This detects protocol and scope mismatches, not semantic coverage or whether a test command is appropriate. A project-wide receipt is not automatically evidence for every module.
- `status` displays historical evidence and local fingerprint changes without running the Kit. Recheck receipts before relying on old results. `delivery_ready` is an evidence gate for configured required checks, not a project-quality or architecture guarantee.

## Local data and safe use

Project paths supported by the CLI stay within the specified root. Symlinks, hardlinked files, and special files such as FIFOs are rejected or reported as excluded by discovery; they are not followed to collect data. These checks do not prevent concurrent filesystem replacement by a process with the same permissions and do not restrict a separately supplied executable. Explicit JSON and note inputs are read from caller-supplied locations and must be regular files.

Scan exclusions and size limits reduce collection; they are not secret detection or anonymization. Even an inventory can reveal private filenames, relationships, source identifiers, or paths. Records retain maps, findings, contracts, decisions, plans, frozen configuration JSON, and check results. Generated links are relative, but caller-supplied text and Kit output or diagnostics may contain machine paths, private data, or credentials. There is no automatic redaction guarantee.

The core records remain local and are not uploaded automatically. Review both `docs/newbie-dev-buddy/` and `.handoff/newbie-dev-buddy/` before sharing or committing them. Configure project-specific exclusions before scanning and avoid entering secrets into notes. Optional tools and configured test commands may have separate network behavior.

Back up current documents and persistent records together. Exclude generated `.handoff/newbie-dev-buddy/` records or `.handoff` from Kit inputs while retaining related source, configurations, tests, and documentation. Complete those changes before acceptance; recording an event must not immediately invalidate the report. The CLI does not silently rewrite Kit configuration to achieve a pass.

Map acceptance writes several files. Per-file replacement is not a cross-file transaction or a power-loss recovery mechanism. After an exception or interruption, inspect the current map, accepted candidate, archive, and lock before retrying; do not assume that all writes completed or were rolled back.

An interrupted writer may leave a lock. Inspect its process and actual project state before removing it; deleting a lock while another writer is active can invalidate coordination.

## Bundled Acceptance Kit

Buddy ships a pinned runtime subset of upstream Acceptance Kit 0.1.2, with its original [MIT copyright and license notice](vendor/acceptance-kit/LICENSE), configuration documentation, and tests. The [bundle manifest](vendor/acceptance-kit/BUNDLE.json) records its source and local patches. The Kit's reported version remains `0.1.2`; version equality alone does not identify the patched code. This subset is part of Buddy and is not distributed as a separate npm package.

The bundled patches reject hardlinked source and evidence files. On a configured step timeout, the runner sends `SIGKILL` to the direct check process. This is not process-tree containment and does not guarantee that every descendant is terminated. File checks also do not prevent concurrent replacement by another process with the same privileges, isolate inherited environment variables, or make configured commands safe.

The patches change `toolHash`, so receipts produced by an earlier external Kit are not automatically valid for the bundle. Recheck such receipts using the original trusted `--kit` directory, or rerun the checks with the bundled runtime. Preserve the old evidence rather than changing its hash or marking it passed under the new runtime.

Basic installation copies the runtime without executing checks, installing Node or npm packages, or starting services. Planning and records require Python 3.9+ without Node or network access; running or checking Kit receipts requires Node.js 22+. Configurations, test programs, and their dependencies still need review and preparation. Bundling a runtime does not authorize running it or establish security certification.

## Installer and CodeGraph

The installer copies only the public package manifest into explicitly selected host directories. It does not overwrite a different existing deployment, upgrade an existing CodeGraph, edit unselected hosts, change PATH, initialize a project index, or relax host trust and tool permissions. Keep manager-owned deployments under their existing manager. Installation is not a sandbox; review the selected executable and resulting configuration.

Enhanced installation reuses a compatible CodeGraph or downloads the pinned official v1.6.2 bundle and verifies the expected SHA-256 before extraction. Downloading requires network access. A checksum verifies bytes against the pinned release manifest, not the security of the upstream program. The independent upstream bundle is retained; this project does not vendor its engine. CodeGraph is [MIT-licensed](https://github.com/colbymchenry/codegraph/blob/v1.6.2/LICENSE); retain its copyright and license notices when redistributing its code or program.

Only strict JSON configuration is merged automatically. Existing Windows configuration receives a manual candidate because Python permission modes do not establish private Windows backup ACLs. On macOS/Linux, backups are stored outside the project under the installation home with private directory/file modes. The installer requires user-controlled directories that are not concurrently replaced; its link checks are not protection against an adversarial process swapping path ancestors. Unknown keys and other servers are retained; a conflicting CodeGraph entry is not silently replaced. Before changing existing JSON, the installer saves a private backup under the user setup directory (directory mode 0700, file mode 0600), never beside project configuration. Backups may contain credentials and are not printed; do not publish them. The enhanced-installation home must remain outside the project. JSONC, TOML, and profile overlays are separate manual candidates. Writing or copying a configuration does not establish which host settings are active, tool availability, or a successful model invocation. Do not automatically enable project MCP, add allowlists, or change a DeepSeek profile to make a candidate active.

CodeGraph's exclusions, indexed roots, trust controls, and network behavior are separate from Buddy's scanner. Confirm the project and permitted indexing scope before running `codegraph init`. Generated server configuration sets `DO_NOT_TRACK=1` and `CODEGRAPH_NO_UPDATE_CHECK=1`; see the [pinned telemetry policy](https://github.com/colbymchenry/codegraph/blob/v1.6.2/TELEMETRY.md). These settings do not prevent the host from sending returned source excerpts to its model provider. A local index is not proof that source remains entirely local.

A PowerShell wrapper and upstream Windows asset choices are provided without a real Windows-host validation claim, and the core workflow still requires macOS/Linux safe directory-relative I/O. Use the complete toolchain inside WSL rather than mixing executables or paths across Windows and Linux. Host-specific configuration fixtures and MCP transport checks do not prove live operation in every supported host.

## Reporting a vulnerability

Use the repository host's private vulnerability reporting channel when available. If no private contact is listed, open an issue requesting one without publishing exploit details, credentials, or private project records. Include a minimal synthetic reproduction, affected version, and expected versus observed behavior once a private channel is established.
