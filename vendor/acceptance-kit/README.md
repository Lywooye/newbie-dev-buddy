# Bundled Acceptance Kit

This directory contains a runtime subset of Acceptance Kit 0.1.2, distributed
under the original [MIT license](LICENSE). Newbie Dev Buddy installs it together
with the Skill; no npm packages, accounts, downloads, or background services are
needed. Running or rechecking acceptance requires Node.js 22+.

Buddy's `run-checks` and `verify` commands use this bundle by default. An explicit
`--kit DIR` selects a trusted external Kit without falling back to the bundle.
The Kit can also be called directly from the Skill root:

```sh
node vendor/acceptance-kit/bin/acceptance.mjs run --project /path/to/project
node vendor/acceptance-kit/bin/acceptance.mjs check --project /path/to/project --receipt /path/to/project/.acceptance/RUN/report.json
```

Prepare real tests and a project configuration before running; see
[configuration](docs/configuration.md) and Buddy's
[verification rules](../../references/verification.md). Running in a copied
workspace is not an operating-system sandbox. Commands inherit the caller's
permissions and environment, and declared dependencies are shared. Only run
commands whose effects you have reviewed.

The original runtime metadata and version are retained. [BUNDLE.json](BUNDLE.json)
records upstream runtime hashes, bundled runtime hashes, and local changes:

- Reject hardlinked source inputs and evidence, including links to old external
  artifacts.
- Send `SIGKILL` on timeout to the direct check process so ignoring `SIGTERM`
  cannot hang that process. This does not contain descendants or external
  services.
- Adapt the help example and configuration guidance to this runtime subset.

Buddy compares the bundled runtime files with this manifest before execution.
This detects accidental changes; it is not a signed supply-chain guarantee or
protection from an attacker who can rewrite the whole Skill. Kit receipts also
bind the actual runtime bytes. Security patches change that fingerprint: recheck
old external receipts using their original trusted `--kit`, or rerun with the
bundle. Never bypass a changed fingerprint to call old evidence current.

This subset is not an independent npm release. The original `package.json` is
retained because receipt fingerprints include it; its upstream packaging scripts
and file list refer to the complete upstream distribution. Use the Node CLI
above, rather than npm installation or packaging commands in this directory.
The copied regression tests use only synthetic temporary projects.
