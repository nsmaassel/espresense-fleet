# Plan: Repeatable project governance

## Implementation

Vendor the eight core workflow skills separately for Codex and Claude, sharing the
PowerShell 7 scripts and templates from pinned GitHub Spec Kit v0.9.5 (FR-002).
Add a concise development entry point and one workflow guide (FR-001). Preserve
constitution 1.0.1. Add explicit per-principle review and task mapping in templates
and migrate existing feature artifacts (FR-003).

Run `python tooling/governance/check_repository.py` and a pinned secret scanner in
CI. Validate recognized private data and artifact structure with negative cases;
review the public diff for information that pattern checks cannot classify
(FR-004, FR-005). Exercise upstream scripts only in disposable repositories and
worktrees, with explicit feature selection and missing-artifact cases (FR-006).

## Constitution Check

- **I — PASS**: Scripts expose commands and JSON results; the guide gives manual
  PowerShell steps for selection, scaffolding, and checks.
- **II — PASS**: This work has no physical device operations or secret prompts.
- **III — PASS**: Upstream assets have pinned provenance; existing configuration
  files and the constitution are preserved. No live fleet state is changed.
- **IV — PASS**: Source assets, specs and fixtures are generic; private configuration
  and credentials remain external. CI and public diff review cover known hazards.
- **V — PASS**: Script smoke tests and governance negative cases provide executable
  evidence. No placement or calibration claims are made.
- **VI — PASS**: The workflow governs this fleet repository and its existing scope.
- **VII — PASS**: Documentation distinguishes automation limits, agent review, and
  hardware validation. No accuracy guarantees are introduced.

Post-design review: all seven principles remain satisfied by this design.
Delivery review and validation outcomes are recorded below.

## Validation evidence

- Windows Python 3.11: 36 tests passed, including 13 governance/scanner tests and the existing flash, provision, and layout tests. Compilation passed.
- `pwsh -File tests/test_specify_scripts.ps1` passed: dry run without mutations, feature creation in a git worktree, missing plan/tasks rejection, setup helpers, existing plan preservation, and explicit feature selection despite a stale selector.
- Gitleaks 8.30.0 (the CI version) passed governance integration tests; local 8.30.1 also passed the full test run. Publishable working files and complete reachable git history scanned clean. Synthetic IRKs were detected and redacted.
- All five PowerShell scripts match their recorded upstream SHA256 hashes. The existing constitution has no diff against the base branch.
- Client discovery paths and instruction pointers were inspected; fresh interactive Codex and Claude skill invocations were not exercised. Script checks do not prove client prompt behavior.

## Analysis and review

All six requirements map to checked tasks. The seven constitutional principles were
reviewed before delivery; no principle changes or unresolved conflicts were found.
No hardware acceptance was inferred from software tests.

Review findings resolved: explicit feature-directory selection prevents stale local
selectors from choosing another feature; local secret scanning exports only
publishable files so ignored dependency fixtures do not cause false positives;
forced tracked private files still fail; deferred roadmap stories remain separate
from implemented requirements. Upstream shell quoting and stale template/context
paths were corrected in the client adapters and recorded as local adaptations.

Remaining limits: static privacy checks cannot classify arbitrary prose or geometry,
and requirement links do not prove coverage quality. These still require review.
CI runs on the pull request; the default branch receives the rules only after merge.
