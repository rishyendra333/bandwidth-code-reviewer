# Acceptance Testing — Results

Nov 5, 2026 · Criteria: [acceptance-rubric.md](acceptance-rubric.md) · Covers the eval pipeline ([bandwidth-reviewer-evals](https://github.com/rishyendra333/bandwidth-reviewer-evals)), the blast-radius prototype ([blast-radius-demo](https://github.com/rishyendra333/blast-radius-demo)), and the [production spec](production-spec.md) and [plan](production-plan.md)

## How it was tested

- **A grader agent** wrote the 30 criteria (weights total 66) *before* any testing, with five must-pass items:
  - unit tests pass offline (U2)
  - the rules-only smoke run passes the gate (RUN1)
  - the prototype runs offline (P1)
  - everything is committed and works from a fresh clone (H1)
  - no secrets in any repo (SEC1)
- **Three tester agents** used the system on isolated copies, with **no API keys**. They used the rules-only reviewer, fake model clients, recorded transcripts, and mock reviewers that emit canned contract output:
  - **Onboarding:** a new teammate following README and RUNBOOK literally, for setup, cases, smoke run, prototype, docs and secrets.
  - **Integrator:** an agent owner plugging a mock reviewer into runs, scoring, comparison, the judge, labeling, the gate and CI.
  - **Adversarial:** crashes, hangs, garbage output, Ctrl-C and resume, bad input, offline, case builders, secret leaks.
- **The grader scored their evidence.** Two forks fixed what they found, the testers re-ran their evidence on the fixed code, and the grader re-scored.

## Scores

| Stage | Score (uncapped) | Grade | Why |
| --- | --- | --- | --- |
| Before fixes | 39.5 / 66 (59.8%) | **59** (blocking) | Must-pass H1 failed: work uncommitted, and the prototype's `--merge-base` flag existed only locally. Also failing: G1, R1, R3, S3, H2 |
| After fixes, not yet committed | 60 / 66 (90.9%) | **59** (capped) | Only H1 is still Fail, which holds the cap |
| After commit + push (Nov 5) | 65 / 66 (98%) | **98** | H1 and G2 now Pass: confirmed from fresh GitHub clones and green Actions runs (below). S2 was fixed too (re-calibrate after tuning) |

### Confirmation run (Nov 5, 2026)

Pushed: blast-radius-demo `898d5ed`, bandwidth-reviewer-evals `aaffb68`, plus this repo. In fresh clones of both code repos, side by side, with no AWS or GitHub tokens set:

- **U1, U2:** `uv sync` works; 74 eval tests pass; `evals validate` gives 0 errors and 1 warning (the small holdout)
- **P1:** the prototype has 69 tests passing, lint is clean, and grammars install
- **RUN1:** the rules-only smoke run writes 13/13 ok rows, and `gate --max-lost 0` passes (exit 0). An empty candidate fails (exit 1)
- **H1:** in all three repos, `git status --short` and `git log origin/main..main` are empty
- **G2:** green on GitHub:
  - evals `test` job: [run 42082854484](https://github.com/rishyendra333/bandwidth-reviewer-evals/actions/runs/42082854484)
  - prototype `ci.yml`: run 42082768510
  - `smoke` printed its skip note, because `REVIEWER_REPO_TOKEN` isn't set yet

## What the testing found and fixed

| Area | Found | Fixed |
| --- | --- | --- |
| **Gate** | Passed reviewers that crashed, timed out, produced an empty file, covered one case, or caught nothing on the 5-catch smoke set (p = 0.0625 can't reach significance) | Fails on no overlap, lower coverage, error rate > 5%, baseline errors, lost catches (`--max-lost 0` in CI), precision below target or its Wilson lower bound, clean-PR noise > 0.1 |
| **Runner** | One bad reply (non-UTF-8, non-executable, malformed log) aborted the batch; timeouts orphaned processes; Ctrl-C kept running queued reviews; torn lines, concurrent writers, shared log folders | Every failure is a row; process-group kills on timeout, Ctrl-C and SIGTERM; clean interrupt and resume; locking; torn-line repair; per-output log folders |
| **Errors** | Tracebacks on missing files, bad YAML, broken recipes, `--workers 0` | One-line errors with the fix |
| **Validation** | Missed split leaks, duplicates, unknown keys, bad ranges and paths, unbuildable recipes, many credential formats; scanned only `cases/` | All flagged; credential patterns broadened and checked on parsed values; `labels/`, `results/` and `baselines/` scanned |
| **Scoring and labels** | Matcher ignored the finding's agent; audited matches lost `expected_id`; blank category samples counted as "right"; queue overwrites; duplicate applies | Agent-aware matching; audit keeps IDs; explicit `ok`; `--force` guard; idempotent apply |
| **Case builders** | Re-mining wiped prepared and confirmed cases; logged-out and offline errors confused; synthetic SHAs depended on the user's git config | Merge on re-mine; clear messages and exit codes; config-independent SHAs |
| **Docs and handoff** | No no-key path; sibling layout and `BLAST_RADIUS_DIR` undocumented; wrong holdout repos; no transfer checklist; no way to re-download data; stale counts | README quickstart without a key; `HANDOFF.md`; `evals download` and `evals split`; corrected counts |
| **CI and security** | Inputs interpolated into shell; `GH_TOKEN` passed to reviewers; unpinned actions; `.env` not ignored | Inputs via env vars; tokens stripped; actions pinned to SHAs; ignore rules |
| **Prototype** | Doctor blamed "model access" when credentials were just missing; the fake-model footer claimed a real model | Skip line; "replayed transcript" footer |
| **Spec and code** | `evals calibrate` missing; the spec's targets not enforced; test-plan gaps | `calibrate` added; targets enforced; supply-chain, retention, operator-access and audit tests in the plan |

## Still open

1. **Turn on CI smoke.** Add the `REVIEWER_REPO_TOKEN` secret to bandwidth-reviewer-evals: a read-only token for blast-radius-demo. The smoke job then runs the gate on every push, not just its skip note. Separately, GitHub warns that the pinned `actions/checkout` and `setup-uv` versions target Node 20. It's a warning only; bump them when convenient.
2. **The holdout is still small** for tests (28 issues), conventions (11) and infra (26), against a target of 50 each. Mine more holdout repos (RUNBOOK step 2), or run `evals plant` once a key is available.
3. **Needs a Bedrock key** (deferred by design):
   - live reviewer runs
   - the two baselines
   - `categorize`
   - the LLM judge, plus the two-person judge audit
   - `plant`
4. The production `bwr` reviewer doesn't exist yet. Its eval entry (`bwr`) and its no-key replay entry (`bwr-replay`) are ready in `reviewers.yml`.
