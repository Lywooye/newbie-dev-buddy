# Module Change Workflow

[简体中文](README.zh-CN.md)

A local Skill and Python CLI for recording module structure, reviewed change plans, implementation events, and Acceptance Kit evidence in project Markdown. It is intended for work that continues across sessions or needs approval of a specific plan revision.

**Version 0.1.1 is experimental.** Only synthetic behavior tests have been demonstrated. There is no comparative evidence that this workflow improves delivery speed, correctness, or safety. The generated workflow document prose is currently Chinese; user-supplied names, contracts, plans, and notes retain their input language.

## What it helps with

- **Stable module IDs:** connect responsibilities, paths, dependencies, and contracts even when names or file locations change. The module graph is supplied and reviewed by the user and agent; it is not automatically discovered from code.
- **A specific accepted revision:** `decide` checks the complete candidate Markdown SHA-256 digest, the latest revision, and tracked project baseline. Implementation records use the separate digest returned for the accepted document.
- **History that survives plan changes:** a new proposal creates a new revision. Accepted plans remain available; `supersedes` identifies an older plan and the constraints being replaced.
- **Separate progress claims:** acceptance, implementation, and verification have distinct records. An accepted plan can still be unimplemented, and an implementation can still be unverified.
- **Existing evidence reuse:** `verify` calls an independently supplied Acceptance Kit's `check` command and records the result for a real project report. It does not introduce another test runner.

These records give the next contributor concrete material to inspect. They do not authenticate human consent, prevent direct file edits, prove that the module design is correct, or establish complete impact and test coverage. Dependency candidates are review prompts, not an exhaustive analysis.

## Requirements and installation

- Python 3.9 or later; the CLI uses only the standard library.
- Node.js is needed only for optional `verify`. That integration was tested with Acceptance Kit 0.1.2, which requires Node.js 22 or later. The Kit is not bundled or installed by this repository; supply a compatible trusted local copy. All other commands work without it.
- A host that supports local Skills is needed to use `SKILL.md` as agent instructions. The Python CLI can also be used directly.

Download or copy this source into a directory named `module-change-workflow`. From its parent directory, install only the Skill files into the root Skills directory:

```sh
(
  set -eu
  skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
  skill_target="$skill_root/module-change-workflow"
  if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
    printf '%s\n' 'Destination already exists; inspect it before updating.' >&2
    exit 1
  fi
  mkdir -p "$skill_root"
  mkdir "$skill_target"
  cp ./module-change-workflow/SKILL.md "$skill_target/"
  cp -R ./module-change-workflow/agents ./module-change-workflow/references \
    ./module-change-workflow/scripts "$skill_target/"
)
```

This refuses to overwrite an existing destination. Follow your host's instructions to reload Skills, then invoke `module-change-workflow` for the relevant project. Direct CLI commands below run from the source directory.

## Synthetic example

This example illustrates the records, not a real approval or implementation. In real work, inspect the current implementation, present the structure and exact proposed revision to the user, and record their actual decision. A note file does not create authorization.

Create an existing `sample-project` directory. Save the following as `map.json` beside the source directory's `SKILL.md`; planned module paths may be absent:

```json
{
  "title": "Synthetic export project",
  "modules": [
    {
      "id": "M-EXPORT",
      "name": "Export",
      "purpose": "Write records to CSV",
      "paths": ["src/export.py"],
      "depends_on": [],
      "contract": "export.write_table uses UTF-8 and writes item_id,score by default."
    }
  ]
}
```

After reviewing the structure, save `structure-note.md` with a clearly labeled **simulated acceptance** for this exercise, then initialize:

```sh
mkdir -p ./sample-project
python3 scripts/module_change.py init --project ./sample-project \
  --map-json ./map.json --decision-note-file ./structure-note.md
```

Save this complete proposal as `spec.json`:

```json
{
  "id": "C-001",
  "title": "Allow an explicit column order",
  "primary": "M-EXPORT",
  "affected": [],
  "location": "export.write_table",
  "plan": "Add optional columns containing item_id and score exactly once each. Preserve the default order when omitted.",
  "acceptance": "Both valid orders produce matching headers and values. Missing, repeated, or unknown columns return an error."
}
```

Create the proposal and extract the returned ID, revision, and candidate digest; do not assume a fixed revision number:

```sh
python3 scripts/module_change.py propose --project ./sample-project \
  --spec-json ./spec.json > ./proposal-result.json
python3 -m json.tool ./proposal-result.json
change_id="$(python3 -c 'import json; print(json.load(open("proposal-result.json"))["change"])')"
revision="$(python3 -c 'import json; print(json.load(open("proposal-result.json"))["revision"])')"
candidate_digest="$(python3 -c 'import json; print(json.load(open("proposal-result.json"))["digest"])')"
```

Read the Markdown at the returned `path`, relative to `sample-project`, and review the complete plan. For this exercise, save `accept-note.md` describing **simulated acceptance of that exact revision**. Then record the decision and extract the new accepted document digest:

```sh
python3 scripts/module_change.py decide --project ./sample-project \
  --change "$change_id" --revision "$revision" --decision accept \
  --expect-digest "$candidate_digest" --note-file ./accept-note.md > ./accepted-result.json
python3 -m json.tool ./accepted-result.json
accepted_digest="$(python3 -c 'import json; print(json.load(open("accepted-result.json"))["accepted_digest"])')"
```

Before editing project files, write the intended scope to `start-note.md` and record the start. After implementing the code and updating relevant module contracts, write what actually changed and any unverified scope to `implementation-note.md`, then record completion:

```sh
python3 scripts/module_change.py record --project ./sample-project \
  --change "$change_id" --revision "$revision" --expect-digest "$accepted_digest" \
  --event started --note-file ./start-note.md

# Implement the reviewed plan and update its module documentation here.

python3 scripts/module_change.py record --project ./sample-project \
  --change "$change_id" --revision "$revision" --expect-digest "$accepted_digest" \
  --event implemented --note-file ./implementation-note.md
python3 scripts/module_change.py status --project ./sample-project
```

Use `interrupted` instead of `implemented` if work stops; describe the actual files, unfinished work, and recovery steps. To revise a plan, submit a complete updated `spec.json` with `propose` again, inspect the returned revision, and obtain a new decision. Do not rewrite an accepted document or reuse its approval for another revision. A replaced accepted revision remains in history but cannot receive new execution or verification records.

## Optional Acceptance Kit check

First run the project's actual acceptance process according to the trusted Kit's documentation. Finish source and module documentation before that run. Exclude generated `.handoff/module-change/` records from Kit inputs so recording a check does not immediately stale its report; do not exclude all `docs/`. The CLI does not change Kit configuration.

For a real report at `sample-project/.acceptance/example-run/report.json` and a trusted Kit at `./acceptance-kit`:

```sh
python3 scripts/module_change.py verify --project ./sample-project \
  --change "$change_id" --revision "$revision" --expect-digest "$accepted_digest" \
  --kit ./acceptance-kit --receipt .acceptance/example-run/report.json
```

The report path is relative to the project root. `verify` invokes `node` on the user-supplied `bin/acceptance.mjs` entrypoint; that executable is part of the trust boundary. It does not run project tests. Passing requires the report's `status` to be `passed` and the Kit check to return `current: true` with `issues: []`. Without a Kit, retain implementation notes and open verification items rather than inventing a passing report.

`status` shows historical verification and content fingerprints without rerunning the Kit. Recheck with `verify` before relying on an old result. Parameter or precondition errors exit with code 1; a completed `verify` that records a failed or stale result exits with code 2. Inspect both JSON output and exit status.

## Records and commands

| Project-relative path | Purpose |
| --- | --- |
| `docs/module-change/MODULES.md` | Current module map and contracts |
| `docs/module-change/changes/` | Accepted plan revisions |
| `.handoff/module-change/drafts/` | Proposed revisions, including rejected ones |
| `.handoff/module-change/decisions/` | Rejection records |
| `.handoff/module-change/records/` | Implementation, interruption, and verification events |
| `.handoff/module-change/CURRENT.md`, `HISTORY.md` | Derived navigation indexes |

Preserve both document and record directories in backups. Only the indexes are rebuildable with `refresh`; the record directory is not disposable cache. Generated index links are relative so they remain usable after moving the project. Records retain user input text and Kit results, which may contain sensitive information or machine-specific paths. There is no automatic anonymization guarantee; inspect them before sharing.

Commands are `init`, `propose`, `decide`, `record`, `verify`, `status`, and `refresh`. See [CLI inputs and behavior](references/cli.md), [workflow rules](references/workflow.md), and [security boundaries](SECURITY.md).

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary synthetic projects and simulated decisions. The Linux CI workflow runs this suite on Python 3.9 and 3.12. This is behavior validation, not evidence of real user consent, production adoption, or comparative performance.

Repository tests use a simulated Kit to check the integration protocol. A real Acceptance Kit 0.1.2 was also checked locally on a synthetic project, including passing, failed-report, and changed-input cases; CI does not supply that external Kit.

Licensed under [MIT](LICENSE).
