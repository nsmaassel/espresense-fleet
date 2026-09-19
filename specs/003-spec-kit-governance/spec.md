# Spec: Repeatable project governance

**Status**: Implemented on main and maintained in place. Constitution remains version 1.0.1.

A new coding session must discover the same project principles and active work,
even when it begins in a workspace containing several repositories. Public tooling
must remain usable with an operator's external private setup.

## Requirements

- **FR-001**: Project instructions MUST route agents among fleet operation, maintenance of an existing feature, creation of a distinct feature, and amendment of project-wide principles. Existing-feature behavior changes load that feature's spec, plan, and tasks. New-feature commands create and consume their artifacts in sequence rather than requiring nonexistent artifacts up front.
- **FR-002**: The repository MUST provide pinned official Spec Kit scripts, templates, and Codex and Claude workflow adapters, preserving the existing constitution.
- **FR-003**: Every Spec Kit feature MUST include a Constitution Check and stable requirement-to-task traceability, with analysis before implementation. The constitution is established at project scope and consumed by downstream feature commands; ordinary feature work MUST NOT recreate or amend it.
- **FR-004**: Deterministic CI MUST check spec structure, requirement links, known private data patterns, and secrets, with limitations documented.
- **FR-005**: Public examples MUST remain fictional; real deployment configuration stays external/private, and credentials stay outside all git repositories.
- **FR-006**: Migration MUST be validated with successful and failing script cases, including worktree discovery and preservation of existing plans.

## Acceptance scenarios

1. A workspace agent reads AGENTS.md, selects the correct work lane, and loads only
   the applicable runbook or feature artifacts; a direct Claude session reaches the
   same rules.
2. On a descriptive branch, explicit feature selection locates existing artifacts.
   Missing plans/tasks fail the prerequisite check without creating them.
3. A new plan includes all constitutional principles and task IDs reference declared
   requirements; malformed or missing links fail the governance checker.
4. Known secret/private fixture violations fail CI; documentation explains that
   arbitrary household data still requires review. No hardware or service changes
   are part of this feature.
5. Public operator documentation leads to setup guides rather than governance
   artifacts. Contributor documentation explains that the constitution is created
   once and automatically consumed by later Spec Kit phases.
