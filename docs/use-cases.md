# Three Newbie Dev Buddy use cases

[简体中文](use-cases.zh-CN.md) · [Project overview](../README.md) · [FAQ](faq.md)

This walkthrough uses one fictional bookmark tool that reads titles, URLs, and tags and exports CSV. Its maps, plan revisions, implementation, and program checks can be reproduced with the [demo script](../examples/bookmark-demo/README.md). Dialogue and decisions are scripted, not actual user feedback or a live model session.

## Plan modules from an idea

**The problem:** “I want to build a small tool, but do not know what to do first or how to divide the code.”

Clarify the first version, then ask your agent to propose responsibilities and relationships. The sample limits its first version to local CSV export and uses three modules:

| Module | Responsibility | Boundary |
|---|---|---|
| Bookmark data `M-STORE` | Read titles, URLs, and tags | No filtering or CSV generation; exports must preserve source data |
| CSV export `M-EXPORT` | Accept a list and generate CSV | Does not store bookmarks |
| Entry point `M-APP` | Receive options and connect reading with export | Does not overwrite user files |

The entry point depends on data and export. The export module accepts a list instead of reading the data file. Review whether each responsibility is understandable, whether the first version includes unnecessary features, and whether original data remains safe. After confirmation, the agent saves the structure with `init`.

**Evidence:** the script supplies this map and the CLI actually saves it. This does not test AI-generated architecture quality. Buddy itself does not design architecture, and three modules are not a universal template.

Try asking your agent:

```text
Use newbie-dev-buddy. I want a local bookmark export tool.
Discuss the first version, then explain module responsibilities and relationships
in everyday language. List uncertainties and show me the map before saving it.
```

## Review and revise a change plan

**The problem:** “The first plan does not match my idea, and I do not want revisions to erase earlier decisions.”

| Revision | Plan and scripted decision | Actual records |
|---|---|---|
| `C-EXPORT` r1 | Export all bookmarks; reject and request tag filtering while preserving default behavior | First-draft Markdown, rejection, and rationale |
| `C-EXPORT` r2 | Add an optional `tag` and entry-point `--tag`; accept | Second draft, revision-specific acceptance, and implementation events; r1 remains |

The second plan changes only the export and entry-point modules. Data reading remains unchanged. Its observable criteria are: `--tag learning` exports two bookmarks, no tag exports three, an unknown tag returns only the CSV header, and original data remains unchanged.

**Evidence:** real CLI calls reject r1, accept r2, and record starting and completing implementation. The script actually modifies the program, checks these behaviors, and compares the first draft's fingerprint to confirm it remains unchanged. These are sample program checks. No Kit is connected, so verification remains `not_run`.

Ask for these review questions alongside a candidate: “Which modules are affected? What behavior must remain? How will completion be observed? What remains uncertain?” To add module verification, prepare a trusted Kit, configuration, and tests under the [verification rules](../references/verification.md), review the check plan, and run it. The demo does not perform this step.

## Continue in a new conversation

**The problem:** “The previous conversation is too long. How does a new agent know where the project stands?”

Have the new agent read current status, the module map, accepted `C-EXPORT` r2, and implementation records, then inspect current code. It should distinguish: r2 is implemented, r1 was rejected, sample behavior was checked, and Kit verification has not run.

In Codex with the Skill installed, try:

```text
$newbie-dev-buddy
Read this project's MODULES.md, C-EXPORT-r2.md, and implementation records,
then check the source. Tell me what is done, what remains unverified,
and which options come next. Do not change code yet.
```

Other agents use their [actual invocation forms](../references/agent-support.md). Records reduce the material you must retell, but missing requirements and stale evidence still need review.

**Evidence:** the replay starts a new CLI process that reads the files and reports r2 implemented, no drift detected for that record, and Kit verification unrun. This demonstrates file-based continuation by a new process, not validated understanding or handoff by a new model. The prompt above is a method to try.

## Inspect the output yourself

From the repository root, choose an output folder that does not already exist:

```sh
python3 examples/bookmark-demo/replay.py --output /tmp/newbie-dev-buddy-bookmark-demo
```

Use Python 3.9+ on macOS/Linux or inside WSL. No model, CodeGraph, or Kit is needed. Existing folders are refused; the script neither installs nor uploads files. See the [reproduction guide](../examples/bookmark-demo/README.md) for output locations.

Inspect generated `evidence.json`: `checks` contains `selected_rows: 2`, `all_rows: 3`, `empty_rows: 0`, `source_data_unchanged: true`, and `first_draft_unchanged: true`; `kit_verification` is `"not_run"` and `real_model_session_tested` is `false`. Also read the generated Markdown. The text and video describe the same synthetic example, not production-project performance.
