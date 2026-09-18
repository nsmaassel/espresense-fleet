# Development workflow

Start an agent in this repository, or explicitly read `AGENTS.md` when a workspace
session routes here. Claude imports it through `CLAUDE.md`; Codex reads `AGENTS.md`.
Then read `.specify/memory/constitution.md` and the active feature's spec, plan, and
tasks. Workspace instructions do not automatically load every child repository.
Keep machine routing and real deployment locations in private workspace instructions.

## Select the feature

Use PowerShell 7 (`pwsh`) on Windows, Linux, or macOS. Existing descriptive branches
can select a numbered feature without renaming their branch:

```powershell
$env:SPECIFY_FEATURE = '001-fleet-foundation'
$env:SPECIFY_FEATURE_DIRECTORY = 'specs/001-fleet-foundation'
pwsh -File .specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks
```

The output identifies the selected directory. Read those files before editing.
`003-spec-kit-governance` covers this workflow; `002-pet-safety` covers the advisory
integration and package. Clear the override before starting a new feature:

```powershell
Remove-Item Env:SPECIFY_FEATURE, Env:SPECIFY_FEATURE_DIRECTORY -ErrorAction SilentlyContinue
pwsh -File .specify/scripts/powershell/create-new-feature.ps1 -DryRun -Json -ShortName example-feature 'Describe the feature'
```

Review the proposed name, then remove `-DryRun` to create the branch and spec in
an isolated worktree. The script changes the current branch; use a clean worktree.
When invoked as a child `pwsh` process it cannot update the caller's environment:
set `SPECIFY_FEATURE` to the returned `BRANCH_NAME` if needed. Alternatively the
specify skill creates the spec directory and writes the ignored local
`.specify/feature.json` selector. Set both overrides above to select an existing feature: `SPECIFY_FEATURE` satisfies
branch validation; `SPECIFY_FEATURE_DIRECTORY` overrides the persisted directory. Keep selectors local, and inspect prerequisite output when switching work.

## Write, analyze, implement

The repo vendors eight upstream skills in each client's own discovery directory:
Codex uses `.agents/skills` and `$speckit-*`; Claude uses `.claude/skills` and
`/speckit-*`. Reopen the project session after adding skills so the client discovers
them. Both use the same scripts and templates. No global skill synchronization is
required. Optional Spec Kit extensions and issue-posting skills are not installed.

1. Use `speckit-specify` for a new stage; use `speckit-clarify` when requirements
   remain ambiguous. Preserve the existing constitution unless a deliberate,
   reviewed principles change requires `speckit-constitution` and a version bump.
2. Use `speckit-plan`. Its `## Constitution Check` addresses principles I-VII with
   evidence or a reason for non-applicability, before implementation and after design.
   Preserve existing plans when resuming; `setup-plan.ps1` skips an existing plan.
3. Use `speckit-tasks`. Requirements use `- **FR-001**:` declarations; checkbox tasks
   have unique stable `T001` IDs; implementation tasks reference applicable requirement IDs. Every
   requirement maps to a task. Deferred roadmap entries may reference their user story
   until requirements are expanded before implementation. Deferred and physical work stays unchecked.
4. Run `speckit-analyze` after tasks and before implementation, including privacy,
   scope, and accuracy claims. Record findings and their resolution in the feature
   artifacts. Unresolved constitutional conflicts block implementation. Use
   `speckit-checklist` when a focused requirements review is useful.
5. Use `speckit-implement` for accepted tasks. Recheck the constitution, run
   `python tooling/governance/check_repository.py`, the applicable automated tests,
   and an in-agent code review before delivery. Record evidence and unfinished work.

The scripts validate paths and prerequisite files. Analyze is an agent review, not
a deterministic proof of meaning. CI checks artifact structure, requirement links,
known privacy patterns and secrets; passing it cannot establish that arbitrary
text or images are free of household information. Review public diffs as well.
Before publishing, run `python tooling/governance/check_repository.py --gitleaks gitleaks`
with the pinned scanner installed. It scans tracked and nonignored new working files;
ignored local dependencies are omitted. For history, run:
`gitleaks git . --config .gitleaks.toml --redact=100 --no-banner --log-opts=--all`.
The CI scanner version is pinned in `.github/workflows/ci.yml`.

Use fictional fixtures; real household setup remains external private configuration.
Passwords and enrollment credentials remain outside every git repository.

## Pinned upstream assets and updates

The repository carries scripts/templates/adapters from GitHub Spec Kit **v0.9.5**,
commit `2262359d967601f864749e359d3e0129e45e94f4`.
[Upstream release](https://github.com/github/spec-kit/tree/v0.9.5),
[MIT license](../.specify/LICENSE.spec-kit), and
[file provenance](../.specify/upstream.json) identify the source. The checked-in
scripts work without installing the CLI. To reproduce scaffolds with `uv`:

```powershell
uv tool install 'specify-cli @ git+https://github.com/github/spec-kit.git@2262359d967601f864749e359d3e0129e45e94f4'
specify init spec-kit-codex-scratch --integration codex --integration-options='--skills' --script ps --no-git --ignore-agent-tools
specify init spec-kit-claude-scratch --integration claude --script ps --no-git --ignore-agent-tools
```

Run these in a disposable directory outside an existing project. Copy only the
listed core scripts, templates, and eight adapters into a review branch. Compare
against the previous pinned assets and reapply the documented local adjustments:
repository rules pointers, PowerShell quoting guidance, reviewed context updates in place of the optional
rewrite extension, installed-skill paths in constitution review, per-principle
Constitution Checks, requirement/task traceability, and tests appropriate to behavior changes. Retain the existing
constitution verbatim unless an approved principles change is part of the work.
Record new upstream version, commit, and original file hashes. Review both clients'
adapters together. Do not initialize with `--force` over an established repository.

Smoke-test create-feature, setup-plan and prerequisite success/failure in a
throwaway git repository and worktree. Check that existing plans are preserved,
nonnumbered branch selection works, and missing plan/tasks fail. Run `pwsh -NoProfile -File tests/test_specify_scripts.ps1`, repository
checks and applicable tests before committing the migration. Agent-context rewriting and
publishing hooks require their own review if introduced later.
