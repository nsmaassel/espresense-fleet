# Development workflow

This guide is for contributors and coding agents. Fleet operators start with the
[setup runbook](runbook.md); they do not need to read the project constitution or
feature artifacts to use the tools.

Start an agent in this repository, or explicitly read `AGENTS.md` when a workspace
session routes here. Claude imports it through `CLAUDE.md`; Codex reads `AGENTS.md`.
Workspace instructions do not automatically load every child repository. Keep
machine routing and real deployment locations in private workspace instructions.

## Choose the development lane

### Maintain an existing feature

Use the existing feature when a change corrects or extends behavior already owned
by its requirements. Locate it by searching specs for the command, module, or
behavior you are changing, then read its `spec.md`, `plan.md`, and `tasks.md`.

- Update `spec.md` when accepted behavior, scope, or status changes.
- Update `plan.md` when the design or validation evidence changes.
- Update `tasks.md` when work is added, completed, or deferred.
- Keep a narrow typo, link, or implementation correction out of the artifacts when
  it does not change feature intent or remaining work.

This preserves the feature's history and avoids a new spec for every maintenance
change. Do not revive a completed task as if it were unfinished; add a traceable
task when the maintenance itself needs to be recorded.

### Add a feature

Create a numbered feature when the work introduces an independently deliverable
capability, a new operator workflow, or a material scope boundary. Run the installed
Spec Kit flow below in a clean feature worktree.

### Amend project principles

The live constitution at `.specify/memory/constitution.md` is created once for the
project and governs every feature. Normal feature work consumes it. Invoke
`speckit-constitution` only for an intentional project-wide principles change;
review the amendment separately, bump its version, and propagate it to dependent
templates and guidance.

The installed Spec Kit skills load the constitution when it constrains their phase.
A contributor may read it directly for a cross-cutting review or a direct maintenance
change, but it is not an extra operator setup step.

## Run the pinned Spec Kit flow

Upstream Spec Kit v0.9.5 defines the core feature flow as specify, plan, tasks,
and implement after the project constitution has been established. This repository
adds analysis as a required pre-implementation gate:

1. `speckit-specify` defines what and why in `spec.md`.
2. `speckit-plan` chooses how and records a per-principle Constitution Check in
   `plan.md`; resolve blocked principles before implementation.
3. `speckit-tasks` creates dependency-ordered, traceable work in `tasks.md`.
4. `speckit-analyze` checks consistency, privacy, scope, and requirement coverage
   after tasks and before implementation. Resolve critical findings in the owning
   artifacts.
5. `speckit-implement` completes accepted tasks and records their state.
6. Run repository checks, applicable tests, in-agent code review, and the feature's
   remaining physical acceptance separately.

Use `speckit-clarify` after specification when requirements are ambiguous. Use
`speckit-checklist` after planning when a focused requirements-quality review will
reduce risk. These are quality gates around the core sequence, not replacements for
its artifacts.

Current upstream Spec Kit includes commands introduced after v0.9.5. Do not document
or invoke one as part of this repository's flow until the vendored assets are
deliberately upgraded and tested together.

Requirements use `- **FR-001**:` declarations. Checkbox tasks have unique stable
`T001` IDs and reference applicable requirement IDs. Every implemented requirement
maps to a task. Deferred and physical work stays unchecked.

## Select an existing feature

Use PowerShell 7 (`pwsh`) on Windows, Linux, or macOS. Existing descriptive branches
can select a numbered feature without renaming their branch:

```powershell
$env:SPECIFY_FEATURE = '001-fleet-foundation'
$env:SPECIFY_FEATURE_DIRECTORY = 'specs/001-fleet-foundation'
pwsh -File .specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks
```

The output identifies the selected directory. Set both overrides when resuming an
existing feature: `SPECIFY_FEATURE` satisfies branch validation and
`SPECIFY_FEATURE_DIRECTORY` overrides the ignored local `.specify/feature.json`
selector. Inspect prerequisite output whenever switching work. Clear the override
before creating a feature:

```powershell
Remove-Item Env:SPECIFY_FEATURE, Env:SPECIFY_FEATURE_DIRECTORY -ErrorAction SilentlyContinue
pwsh -File .specify/scripts/powershell/create-new-feature.ps1 -DryRun -Json -ShortName example-feature 'Describe the feature'
```

Review the proposed name, then remove `-DryRun` to create the branch and spec in an
isolated worktree. The script changes the current branch; use a clean worktree. A
child `pwsh` process cannot update its caller's environment, so set the returned
feature values explicitly when needed.

## Validate before delivery

Run:

```text
python tooling/governance/check_repository.py
python -m unittest discover -s tests -v
pwsh -NoProfile -File tests/test_specify_scripts.ps1
```

Use applicable narrower tests while iterating. Before publishing, run
`python tooling/governance/check_repository.py --gitleaks gitleaks` with the pinned
scanner installed, then scan reachable history with
`gitleaks git . --config .gitleaks.toml --redact=100 --no-banner --log-opts=--all`.
CI pins the scanner version in `.github/workflows/ci.yml`.

The checks validate paths, artifact structure, requirement links, known privacy
patterns, and secrets. They cannot establish that arbitrary prose, geometry, images,
or radio claims contain no household information. Review the public diff. Keep real
household setup in external private configuration and credentials outside every git
repository.

## Pinned upstream assets and updates

The repository carries PowerShell scripts, templates, and eight client adapters from
[GitHub Spec Kit v0.9.5](https://github.com/github/spec-kit/tree/v0.9.5), commit
`2262359d967601f864749e359d3e0129e45e94f4`. The
[source license](../.specify/LICENSE.spec-kit) and
[provenance manifest](../.specify/upstream.json) record the imported files. Codex
discovers `.agents/skills`; Claude discovers `.claude/skills`. Reopen the project
session after adding or upgrading skills.

Upgrade the pinned set in a disposable directory and review both clients together.
Preserve project-local Constitution Checks, requirement/task traceability, PowerShell
quoting fixes, context-update behavior, provenance, and the live constitution. Do
not initialize with `--force` over this repository. Smoke-test feature creation,
worktree discovery, existing-plan preservation, explicit selection, and missing
artifact failures before merging an upgrade.
