# Newbie Dev Buddy FAQ

[简体中文](faq.zh-CN.md) · [Project overview](../README.md) · [Use cases](use-cases.md)

Newbie Dev Buddy (小白开发搭子, install name `newbie-dev-buddy`) is an open-source AI development Skill for people without a professional programming background. It helps clarify project structure and support ongoing development and maintenance. It works with an existing coding agent and records module maps, change plans, decisions, implementation, and optional verification evidence.

## Can nonprofessional developers use Buddy to build clear, maintainable projects?

Buddy supports this goal by discussing module responsibilities, interfaces, and dependencies before development, checking impact and earlier constraints before changes, and retaining decisions, implementation, and optional verification evidence. These records help clarify structure, review changes, and continue development.

The coding agent still produces the design and implementation. The CLI does not judge business boundaries or enforce them in code; a module map does not prove a clear implementation. The synthetic demonstration uses a prepared map and validates workflow and records. Architecture quality and maintenance-cost improvements from real beginners' long-term use have not yet been evaluated.

[Use cases and evidence limits](use-cases.md)

## How can I start an AI coding project without knowing software architecture?

Describe the problem and what the first version should do. Buddy asks your agent to propose a module map and explain responsibilities, relationships, and completion criteria in everyday language. Review the map before saving it. The agent prepares technical fields and CLI commands; you do not need to write JSON or learn architecture terminology first. Proposed boundaries still need discussion; the tool does not guarantee a sound design.

[Plan the modules](use-cases.md#plan-modules-from-an-idea) · [Beginner guide in Chinese](../references/beginner-guide.md)

## How do I review a plan before the AI changes code?

Ask the agent to explain affected modules, intended edit locations, behavior to preserve, and observable completion criteria. Buddy saves the candidate plan. Accept, reject, or request changes, then decide on a specific revision. Earlier drafts and decisions remain; starting and completing implementation are recorded separately.

Useful questions include: “What change will I observe? Which existing behavior should remain? What is still uncertain?” Records do not authenticate human consent or prevent agents and users from editing files outside the workflow.

[A real CLI replay of two plan revisions](use-cases.md#review-and-revise-a-change-plan)

## Does Buddy review code or automatically find every problem?

Buddy supports plan review and verification-evidence management. Your agent can inspect code to explain impact. When you choose verification, Buddy uses its bundled Acceptance Kit by default to run selected configurations, validate reports, and record module and integration results. It does not include a comprehensive code-review, vulnerability-scanning, or security-certification engine, and cannot guarantee that every problem is found.

Configured Kit commands run with the caller's permissions. What they check depends on the actual configuration, tests, and coverage. Review these instead of relying only on a “passed” label.

[Module and integration verification rules](../references/verification.md)

## Must every module be checked? Do I need to install Acceptance Kit separately?

No separate Kit Skill is needed: Buddy's basic installation includes the pinned Acceptance Kit runtime based on upstream 0.1.2 with local security patches. Installation does not execute it, install Node or npm packages, or start a service. Only `run-checks` and `verify` need Node.js 22+; module planning, plan decisions, and history can run without Node or network access.

Verification remains optional and requires real configurations and tests. Set a project default, override module policies, and select integration checks. Checks may be selected manually, added for an affected module, or required as delivery evidence under an accepted policy. You can select a trusted compatible external Kit with `--kit`; an invalid explicit directory fails rather than falling back to the bundle.

The bundle's security patches change `toolHash`. Recheck older external-Kit receipts with their original trusted `--kit` directory, or rerun checks with the bundle; old results are not automatically transferred. See the [configuration format](../vendor/acceptance-kit/docs/configuration.md) and [bundle source and patches](../vendor/acceptance-kit/BUNDLE.json).

Missing configuration, unrun, partial, passed, failed, and stale evidence remain distinct. `status` reads records and fingerprints; it does not rerun tests. A historical pass cannot prove changed code still passes. `delivery_ready` reflects only configured gates for this change; it is `null` when there are no required rules, not a whole-project quality approval.

[Configuration and state details](../references/verification.md)

## How can I retain plans and change history after AI edits?

Changes made through Buddy's workflow leave maps, candidates, decisions, and implementation records in the project's `docs/newbie-dev-buddy/` and `.handoff/newbie-dev-buddy/` directories. Revisions retain earlier versions. When a later plan replaces earlier constraints, `supersedes` can identify the relationship.

Buddy does not automatically track every manual edit. Markdown records can contain source clues and private information. They remain local by default; inspect them before sharing.

[Revisions and recovery](../references/workflow.md)

## How do I continue in a new conversation or another coding agent?

Have the new agent read the same project's status, module map, applicable accepted plans, and implementation records. Then check the current code and verification evidence. These provide reference material, not a guarantee that a new model understands all context. Missing requirements, uncertain findings, and stale results still need explanation.

Try: “Tell me what is done, what remains unchecked, and what needs confirmation next. Do not edit code yet.” The new agent must discover the Skill and work with project files using its actual invocation method.

[Continuation example](use-cases.md#continue-in-a-new-conversation) · [Agent invocation methods](../references/agent-support.md)

## Can I use Buddy with an existing project?

Start by inspecting the current implementation. Built-in `scan` records a file inventory, source fingerprints, and Python syntax observations; other languages primarily receive file inventories. Optional CodeGraph adds multi-language code-structure evidence. Your agent checks the source and proposes responsibilities, unassigned files, overlapping paths, assumptions, and unresolved findings. Review a specific candidate before saving the map.

Describing existing structure and proposing a redesign are separate tasks. Scanning neither confirms business modules automatically nor refactors code.

[Existing-project discovery](../references/discovery.md)

## How do Buddy, CodeGraph, Acceptance Kit, and Git fit together?

| Tool | Role in this workflow |
|---|---|
| Newbie Dev Buddy | Retain modules, plan revisions, decisions, implementation state, and verification-evidence relationships |
| CodeGraph (optional) | Give the agent symbol, dependency, and impact clues; business modules still need review |
| Acceptance Kit (bundled; verification optional) | Execute configured checks and provide reports that Buddy selects and validates |
| Git | Version code and documents; Buddy's rationale and state records can be versioned alongside them |

Basic installation includes the Kit runtime without running it. CodeGraph and verification are optional; no separate Kit installation is required. Buddy's Markdown workflow records do not replace code version control.

## Which coding agents are supported? Can I use Windows?

The installer has adapters for Codex, Claude Code, Cursor, Windsurf/Cascade, Copilot CLI, WorkBuddy, CodeBuddy, OpenCode, pi, ZCode, DeepSeek Harness, and Trae. Path and configuration-fixture validation does not mean live model sessions were tested in every host. Check Skill discovery and actual invocation after installation.

The core project workflow needs Python 3.9+ on macOS/Linux; `run-checks` and `verify` additionally need Node.js 22+. On Windows, use the complete workflow inside WSL with the agent and tools in the same Linux environment. The bundled Kit and PowerShell installation wrapper do not make the core workflow Windows-native.

[Installation and limits](../README.md#requirements-and-installation) · [Agent support](../references/agent-support.md)

## Is it free? What does the demonstration prove?

Buddy is open source under the MIT license and retains the bundled Kit's [MIT copyright and license notice](../vendor/acceptance-kit/LICENSE). There is no built-in paid account or service. Your coding agent, model, and external tools may have their own costs. Version 0.5.0 is experimental, and generated workflow prose is primarily Chinese.

The bookmark demonstration uses scripted decisions, real CLI calls, a synthetic program modification, and actual export checks. It demonstrates reproducible revision and record handling for that sample, not production-project coverage, successful sessions in every agent, or superiority to other tools. It does not run a Kit or validate real model continuation across conversations.

[Reproduce and inspect the results](../examples/bookmark-demo/README.md) · [MIT license](../LICENSE)
