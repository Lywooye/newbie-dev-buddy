# Newbie Dev Buddy

[简体中文](README.zh-CN.md)

A local Skill for beginners building software with AI. Describe what you want to build; your coding agent proposes a module plan and development approach for review before implementation. New projects start with module design; existing projects start with code inspection. Reviewed maps, accepted plans, implementation events, and optional acceptance evidence stay in Markdown for later sessions.

The Chinese product name is **小白开发搭子**. Install and invoke the Skill as `newbie-dev-buddy`; the companion Python CLI maintains the records.

**Version 0.3.0 is experimental.** The workflow has synthetic validation and small external-Kit integration examples; it has not been evaluated on a user's production project or shown to outperform other tools. Generated workflow prose is currently Chinese; supplied names, contracts, plans, and notes retain their language.

## What it helps with

- **Design modules before starting a new project.** The agent proposes responsibilities, inputs, outputs, and relationships in plain language. After review, `init` saves the accepted initial map. Planned code paths may not exist yet; plans and implemented states remain separate. The CLI itself does not design architecture.
- **Start with existing code.** `scan` records a structural inventory and fingerprints. An agent or contributor checks code and groups responsibilities; `map-propose` makes that map reviewable, including differences, unassigned files, and overlapping paths. Python symbols and imports are syntax observations; other languages currently receive file inventory only. The CLI does not automatically infer business modules or refactor code.
- **Keep structure history.** Accept a specific map revision, retain earlier maps, and preserve module IDs through renames and moves. Splits, merges, and retirements require explicit lineage; retired IDs cannot be recycled.
- **Approve an exact plan.** Change decisions check the complete candidate Markdown digest, latest revision, and tracked baseline. Accepted revisions remain available when a later plan replaces them.
- **Choose module checks.** Set a project default, override a module, and add cross-module integration checks. Each change proposal freezes the configuration SHA and JSON content, required steps, and declared inputs. Configured source/test inputs must exist and remain covered before proposing; prepare new test files first. A passing project report does not automatically mark every module as checked.
- **Keep claims separate.** Accepted, implemented, and verified are different states. Missing, partial, failed, historical, and stale evidence remains visible.
- **Reuse a trusted Kit.** `run-checks` actually runs selected existing Acceptance Kit configurations; `verify` rechecks an existing report. No new test runner, server, account, or database is required.

The records support review and handoff. They do not authenticate consent, prevent direct file edits, prove correct architecture, or establish exhaustive impact and test coverage. `delivery_ready` requires required checks and relevant configured interface checks for required modules to pass; any executed failed or stale check blocks that gate. With no required rules it is `null`, not a claim that the whole project is correct.

## Requirements and installation

- Python 3.9 or later; the core CLI uses only the standard library. Discovery currently requires safe Unix directory-relative I/O on macOS or Linux.
- Node.js and a trusted compatible Acceptance Kit are optional, needed only for `run-checks` and `verify`. Integration uses Acceptance Kit 0.1.2, which requires Node.js 22 or later. The Kit is not bundled or installed automatically.
- A local Skill host is needed for the agent instructions; the CLI also works directly. CodeGraph and Understand Anything are optional analysis sources, not dependencies.

Copy the source into a directory named `newbie-dev-buddy`. From its parent, install the Skill without overwriting an existing deployment:

```sh
(
  set -eu
  skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
  skill_target="$skill_root/newbie-dev-buddy"
  if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
    printf '%s\n' 'Destination already exists; inspect it before updating.' >&2
    exit 1
  fi
  mkdir -p "$skill_root"
  mkdir "$skill_target"
  cp ./newbie-dev-buddy/SKILL.md "$skill_target/"
  cp -R ./newbie-dev-buddy/agents ./newbie-dev-buddy/references \
    ./newbie-dev-buddy/scripts "$skill_target/"
)
```

Reload Skills according to your host's instructions. If a Skills manager owns the deployment, update it through that manager rather than overwriting its files.

## Use with an agent

Start with the [beginner guide in Chinese](references/beginner-guide.md), including setup, new projects, changes, and continuing in another conversation.

Invoke `$newbie-dev-buddy` for the intended project:

For a new project:

> I want to build a tool that does…. Help me define the first version, propose its modules, and explain how they work together in plain language. After I confirm the plan, save the structure and start development.

For an existing project:

> Organize this project's existing modules and relationships. Separate code-confirmed findings from assumptions and gaps. Show me the proposed map and available module checks before saving the accepted structure.

The workflow is:

```text
Clarify new-project requirements or inspect existing code → propose a module map → accept or revise
→ propose a change and check plan → accept that revision
→ implement → run selected checks → recheck and record evidence
```

Discovery documents the current implementation. A suggested redesign becomes a separate change proposal. Scanning does not install tools, execute project scripts, redirect to another worktree, or upload code.

The coding agent prepares input files, commands, and technical fields. You review what will be built, what it affects, and how completion will be checked. The CLI reference below supports direct use and troubleshooting.

## Direct CLI

The examples below use an existing project. For a new project, save the reviewed initial module map with [`init`](references/cli.md#扫描地图候选与接受).

Commands below run from this source directory. Paths, names, and SHA placeholders are synthetic; get actual scan paths, revisions, and digests from JSON command results.

```sh
python3 scripts/newbie_dev_buddy.py scan --project ./sample-project --exclude private
python3 scripts/newbie_dev_buddy.py map-propose --project ./sample-project \
  --scan .handoff/newbie-dev-buddy/discovery/S-SCAN.md --map-json ./map.json
```

Keep generated map/spec JSON under the project's `.handoff/newbie-dev-buddy/inputs/` or outside the project in a temporary directory, so generating transport inputs does not invalidate the scan. The map and versioned Markdown remain authoritative.

Read the complete candidate. After the user accepts that exact version, save the actual decision in `map-note.md` and use its returned revision and digest:

```sh
python3 scripts/newbie_dev_buddy.py map-decide --project ./sample-project \
  --revision MAP_REVISION --expect-digest MAP_CANDIDATE_SHA \
  --decision accept --note-file ./map-note.md
```

The first acceptance creates `docs/newbie-dev-buddy/MODULES.md`. Later acceptance retains the old map and updates the current one. A note file records a decision; it does not itself create permission.

Prepare a complete `spec.json` with the change ID, primary and affected modules, location, plan, and observable acceptance conditions. Then use `propose`, review and `decide`, record `started`, implement, and record `implemented`. See [input schemas and examples](references/cli.md).

After selected checks are authorized and a trusted Kit is available:

```sh
python3 scripts/newbie_dev_buddy.py run-checks --project ./sample-project \
  --change C-001 --revision REVISION --expect-digest ACCEPTED_MD_SHA \
  --kit ./acceptance-kit --check-id module:M-EXPORT
```

Or run the Kit through the project's existing process, then recheck its real report:

```sh
python3 scripts/newbie_dev_buddy.py verify --project ./sample-project \
  --change C-001 --revision REVISION --expect-digest ACCEPTED_MD_SHA \
  --kit ./acceptance-kit --receipt .acceptance/example-run/report.json \
  --check-id module:M-EXPORT
```

`run-checks` rechecks the frozen configuration, then executes every step in each selected configuration with the invoking user's permissions; it is not a sandbox. Changing check commands after starting requires a revised, accepted proposal. `verify` invokes the supplied Kit's checker but does not run project tests. Use trusted configurations and exclude generated `.handoff/newbie-dev-buddy/` records from Kit inputs without excluding all relevant documentation. No Kit means open verification items, not an invented passing report.

`status` is read-only and does not rerun the Kit. Recheck historical evidence before relying on it. `refresh` rebuilds indexes only; it does not rescan modules. Parameter errors exit with code 1; completed failed or stale verification exits with code 2. Inspect JSON and exit status.

## Records and handoff

Current structure lives in `docs/newbie-dev-buddy/MODULES.md`; accepted changes in `docs/newbie-dev-buddy/changes/`. Scans, map history, candidates, decisions, and events live under `.handoff/newbie-dev-buddy/`. Back up both directories; only `CURRENT.md` and `HISTORY.md` navigation indexes can be regenerated.

Updating the map does not rewrite accepted changes or silently expand their tracked scope. An unscoped passing report is retained as overall historical evidence, not assigned to every module.

Records are local by default. Relative links help portability, but inputs, paths, findings, and Kit output may contain private information. There is no automatic anonymization; inspect records before publishing.

See [discovery](references/discovery.md), [workflow](references/workflow.md), [module verification](references/verification.md), [CLI](references/cli.md), and [security](SECURITY.md).

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary synthetic projects and simulated decisions. CI runs the suite on Linux with Python 3.9 and 3.12. Repository fixtures check the Kit protocol; external-Kit examples are separate from CI and do not establish production readiness or comparative performance.

Licensed under [MIT](LICENSE).
