---
name: stage
description: Run one stage of the roadmap in docs/plan.md end-to-end (analyze → decompose → implement → test → review → docs → commit). Use when the user asks to start or continue a stage, e.g. "/stage 3".
---

# Run a roadmap stage

Stage to run: `$ARGUMENTS` (a number from docs/plan.md § 1). If it is missing, ask which stage.

## 1. Analyze
- Read the stage row in `docs/plan.md`, the related sections of the design docs and the acceptance criteria it must satisfy (`docs/architecture.md § 1.3`).
- State in 3–6 bullets what will be built, which design decisions apply and the risks or open questions. If a design decision has to change, say so **before** coding and update the doc in the same stage.

## 2. Decompose
- Create a branch `stage/<n>-<short-name>` from `main`.
- Break the stage into small tasks, each one ending in a commit (model/migration, service, router, tests, docs…).

## 3. Implement → verify, per task
- Implement following `CLAUDE.md` (layering, access policy, no mass assignment, keys from server ids, enqueue after commit).
- Write or extend the tests together with the code, including negative authorization cases.
- Run the `verify` skill. Fix failures before moving on. Never move on with red tests.
- Commit with the `commit` skill.

## 4. Review
- Run the `code-reviewer` agent on the stage diff (`git diff main...HEAD`).
- If the stage touches auth, access, uploads, media, moderation or admin, also run the `security-reviewer` agent.
- Fix blockers and majors (with tests). List the minors you deferred and why.

## 5. Close the stage
- Update the docs whose behaviour changed (and the status notes in `docs/plan.md`).
- Report to the architect: what was built, the real test summary, review findings and their resolution, deviations from the design, and what the next stage needs.
- **Wait for the architect's approval** before merging (`git merge --no-ff`) and tagging `stage-<n>`. Never push without explicit permission.
