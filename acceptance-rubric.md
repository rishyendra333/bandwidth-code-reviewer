# Acceptance rubric: eval pipeline, blast-radius prototype, spec and plan

Nov 4, 2026 · Handoff to Bandwidth: Fri Nov 13, 2026 · Graded: (1) `bandwidth-reviewer-evals`, which must be ready to run; (2) the blast-radius prototype (`blast-radius-demo/.github/bandwidth-reviewer`), the one reviewer that exists today; (3) `production-spec.md` and `production-plan.md` as the product blueprint. The product code (`bwr`) doesn't exist yet and isn't graded.

## Ground rules for testers

- **No keys.** Every verdict comes from checks that need no Bedrock key. Checks marked **Key later** go in the report as *Deferred (key)* with the exact command, and they don't count toward the score.
- **Fresh clones.** Test from fresh GitHub clones in a scratch folder, never in the authors' working trees. If a clone lacks files (H1 fails), copy the authors' trees into the scratch folder (skip `.venv`, `data/`, `runs/`), finish the other criteria, and label each piece of evidence `clone` or `copy`.
- **GitHub login is optional.** It's your own account, not an API key. It's only needed for B1, for viewing Actions runs (G2), and for any private repo.
- **Clean up afterwards.** Revert scratch edits to `reviewers.yml`, `targets.yml`, `cases/` and `labels/` (`git checkout . && git clean -fd`).

```bash
export T=$HOME/bwr-acceptance && mkdir -p $T/evidence && cd $T
for r in bandwidth-reviewer-evals blast-radius-demo bandwidth-code-reviewer; do git clone https://github.com/rishyendra333/$r; done
unset AWS_BEARER_TOKEN_BEDROCK AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE EVAL_MODEL EVAL_JUDGE_MODEL
env | grep -cE '^(AWS_|EVAL_)'      # must print 0: paste it in the report header
(cd blast-radius-demo/.github/bandwidth-reviewer && make setup && make fixtures)
(cd bandwidth-reviewer-evals && uv sync --group dev --extra judge)
```

Run `evals` commands from `$T/bandwidth-reviewer-evals` and `make` from `$T/blast-radius-demo/.github/bandwidth-reviewer`. Appendix A has the mock reviewer (`mock`) that several criteria use. Verdicts are **Pass**, **Partial**, **Fail** or **N/T** (not testable here, with the reason). W is the weight (1–3); **MP** marks a must-pass item.

## Criteria

### Setup & onboarding

**U1 · Install, help and doctor on a clean machine** · W2
- **Pass:** `uv sync` succeeds on Python 3.12. `uv run evals --help` lists every command in the README's Commands table. `uv run evals doctor` prints one line per check, marks Bedrock ❌ with the `export AWS_BEARER_TOKEN_BEDROCK=…` fix, exits 1 and shows no traceback. `doctor --live` without a key also ends cleanly.
- **Partial:** works only after an undocumented step, or a README command is missing from `--help`. **Fail:** install or `doctor` crashes.
- **Evidence:** each command with `echo $?`, and the `doctor` output. **Key later:** `doctor --live` prints "Bedrock model … answers".

**U2 · Unit tests pass offline, both repos** · W3 · **MP**
- **Pass:** `uv run --group dev pytest -q` (evals), plus `make test` and `make lint` (prototype), pass with 0 failures, no AWS variables and the network off (turn off Wi-Fi after setup). The prototype's test count matches its docs (README says 68; spec C.2 and plan §1 say 69): either the count matches, or the docs are corrected.
- **Partial:** tests pass only with the network on, or the counts disagree. **Fail:** any test fails or errors.
- **Evidence:** each run's last summary line, the `env | grep` output, and how the network was turned off. **No key:** by design (FakeBedrock clients, monkeypatched `gh_json`, temporary git repos).

### Case data

**C1 · Cases validate and the counts are honest** · W2
- **Pass:** `uv run evals validate` exits 0 with 0 errors, and the docs explain every warning (small holdout, unprepared SHAs). `uv run evals stats` matches the README's "Cases today" table (fixture 13, swe-prbench 350, qodo 100, mined 84, traced 74, tool 40, planted 0). `stats --split holdout` shows no swe-prbench, qodo or fixture case, and synthetic cases are counted separately.
- **Partial:** a count differs from the README, or a warning is unexplained. **Fail:** `validate` reports errors. **Evidence:** all three outputs.

**C2 · Spot check of 12 cases** · W2
- **How:** pick 2 random cases per source (`ls cases/<src> | sort -R | head -2`). For each, check that: base, head and merge_base are 40-hex SHAs (for fixtures, branches that exist in `../blast-radius-demo`); `pr_url` and `evidence_url` open the right public PR or comment; each expected file exists at head (`git -C <repo or data/mirrors/…> cat-file -e <head>:<file>`); `label_quality` and `split` are set; clean cases have no `expected` items.
- **Pass:** at least 11 of 12 cases pass every check. **Partial:** 9–10. **Fail:** 8 or fewer. **Evidence:** a 12-row ✓/✗ table. **No key:** public pages and git only.

### Running reviewers

**RUN1 · Rules-only smoke run, end to end** · W3 · **MP**
- **Pass:** `time uv run evals run --reviewer blast-radius-rules --set smoke --out $T/smoke.jsonl` writes 13 rows, all `ok`, in under 2 minutes. `uv run evals score $T/smoke.jsonl --source fixture` prints a report. `uv run evals gate baselines/smoke-blast-radius-rules.jsonl $T/smoke.jsonl --source fixture` prints **PASS** and exits 0. A second run (`--out $T/smoke2.jsonl`) gives identical findings.
- **Partial:** one fixture errors, or the run needs an undocumented step. **Fail:** the run can't complete.
- **Evidence:** the status totals, the `time` output, the gate table with its exit code, and a diff of the two runs' findings.

**RUN2 · The contract path, with a mock reviewer** · W3
- **Pass:** with the Appendix A mock, `uv run evals run --reviewer mock --set smoke --agents blast-radius --out $T/mock-ok.jsonl` records 13 `ok` rows, and unknown fields in its JSON are ignored (contract rule 4). One log in `runs/_work/mock/` shows 40-hex SHAs for base, head and merge base, `--agents=blast-radius`, and the case title as a single argument. `MOCK_MODE=partial` gives `partial: tests error` rows. Two runs of `--set dry-run --limit 3` pick the same case IDs (this fetches public mirrors), and `--agent blast-radius` narrows the set.
- **Partial:** one sub-check fails. **Fail:** a contract-writing command can't run as a reviewer.
- **Evidence:** totals per mode, one log's `$ …` line, both ID lists, and what `--reviewer bwr` does when `BWR_REVIEWER_CMD` points at the mock and there's no key. It's expected to be refused, because `bwr` is `needs_model: true`; S3 tracks this. **Key later:** the real `bwr review --agents blast-radius` on the fixtures (plan day 1).

### Scoring & comparison

**SC1 · Score and compare give correct numbers** · W3
- **Pass:** all five hold:
  - (a) `uv run evals score results/2026-11-02-blast-radius-fixtures/blast-radius.jsonl --source fixture` reproduces that folder's README (10/10 caught, 41/42 precision, 0 clean-PR comments), or a documented matcher change explains the difference.
  - (b) For `$T/mock-ok.jsonl`, the tester hand-counts from the case YAMLs which findings should be matched, wrong (inline on a clean case, or on a `must_not_flag` item) and unjudged, and `score` agrees exactly.
  - (c) With `--runs 3`, `MOCK_MODE=once` leaves fixture-rounding *not caught* and `MOCK_MODE=twice` catches it (more than half the runs).
  - (d) Rates show 95% intervals that stay within 0–100%.
  - (e) `evals compare X X` shows no wins or losses, and baseline vs the `MOCK_MODE=empty` run shows the losses.
- **Partial:** (a), (d) or (e) is off. **Fail:** (b) or (c) is wrong. **Evidence:** the hand-count table beside the `score` output, and the `compare` output.

### Judge & human labeling

**J1 · The judge fails cleanly without a key, and its logic is tested** · W2
- **Pass:** `uv run evals judge $T/mock-ok.jsonl` exits nonzero with a one-line fix (set `EVAL_MODEL` or the key), with no traceback and nothing written to `labels/verdicts.jsonl`. A file with nothing unmatched prints "Nothing to judge". These tests pass: `test_judge_parses_json_and_falls_back_to_unclear`, `test_verdicts_turn_unmatched_into_matched_valid_or_wrong` and `test_human_verdict_beats_model_verdict`. In `judge.py`, the prompt carries a written rubric and doesn't reveal the reviewer or its version.
- **Partial:** a traceback instead of a message, or the prompt leaks the reviewer. **Fail:** the judge tests are missing or fail. **Key later:** `evals judge` on a real run, with a judge model different from the reviewer's.

**J2 · People: label queue and judge audit** · W2
- **Pass:** both paths work:
  - **Label queue:** `uv run evals labels export $T/mock-ok.jsonl` writes `labels/queue.yml` with one row per unjudged finding. Fill 2 rows (`valid` and `invalid`) and `labels apply` reports 2. `score` then moves both out of unjudged: augmented precision changes, grounded doesn't.
  - **Judge audit:** append 25 fabricated rows with unique keys (`{"key": "k1", "case_id": "fixture-hub", "by": "model", "verdict": "valid"}`) to `labels/verdicts.jsonl`, run `judge-audit export -n 25`, and fill `verdict_a` and `verdict_b`. With 10 rows filled, the report says "Not trusted yet" and exits 1. With all 25 at ≥90% agreement, it says "Trusted" and exits 0. Rows where the two people disagree aren't scored.
- **Partial:** one path fails. **Fail:** labels can't make the round trip. **Evidence:** queue row count, `apply` output, `score` before and after, both audit reports with exit codes. **Key later:** the real 40-row audit by two people (plan day 3).

### Case builders

**B1 · mine and trace (GitHub-based)** · W1
- **Pass:** offline, `test_trace_builds_a_case_on_the_introducing_pr` and `test_patch_line_parsing_and_ranges` pass, and without a `gh` login both commands fail with a login hint, not a traceback. With a login, `uv run evals mine fastapi/fastapi --limit 20 --since 2026-07-01` and `uv run evals trace fastapi/fastapi --since 2026-05-01 --limit 5` write cases that pass `validate`, say `label_quality: weak`, link to their source, and land in the split their repo hash gives. A re-run doesn't duplicate them.
- **Partial:** only `trace` could be verified (`mine` has no offline test of its mining loop, and no login was available). **Fail:** a crash, or the new cases fail `validate`.

**B2 · inject-secrets** · W2
- **Pass:** the `test_secret_formats_*`, `test_build_is_deterministic_*`, `test_validate_rejects_literal_credentials` and `test_ensure_rebuilds_synthetic_head_*` tests pass. `uv run evals inject-secrets --split holdout --limit 2 --negatives 1` writes 3 files to `cases/tool/`, and `validate` passes. Grepping the new files with the `CREDENTIAL` regex from `validate.py` finds nothing; they hold only seeds such as `secret:aws:17`. `evals run --reviewer blast-radius-rules --set release --only <new id>`, run twice with `data/mirrors` deleted in between, logs the same synthetic head SHA. Adding an AWS-key-shaped string (`AKIA` plus 16 capitals) to a scratch case makes `validate` exit 1 and name the file.
- **Partial:** everything works, but determinism wasn't shown. **Fail:** a literal secret ends up in a case file, or `validate` accepts the planted string.

**B3 · plant** · W1
- **Pass:** `uv run evals plant --menu` lists bug types per agent offline. `uv run evals plant --agent security --limit 1` without a key exits with the credentials message, no traceback and no files written. `test_plant_applies_*` and `test_plant_rejects_code_that_does_not_parse` pass.
- **Partial:** the menu or the message is wrong. **Fail:** the tests fail. **Key later:** 10 planted cases per agent that parse, validate and pass a person's spot check (0 exist today).

**B4 · categorize** · W1
- **Pass:** `test_categorize` and `test_sort_with_model_writes_back_and_caches` pass. `evals categorize` without a key exits with the credentials message. `--export-sample 5` and `--apply-sample` run offline, say what they did ("Nothing checked yet" when nothing is model-sorted), and leave `validate` passing.
- **Partial:** a message is unclear. **Fail:** the tests fail, or applying a sample breaks case files. **Key later:** a full `categorize`, then a person's 50-item check with the model right at least 85% of the time (RUNBOOK step 3).

### Gate & CI

**G1 · The gate blocks regressions** · W3
- **Pass:** all six hold: (a) baseline vs itself gives PASS, exit 0; (b) baseline vs the `MOCK_MODE=empty` smoke run gives FAIL, exit 1; (c) a scratch targets file with `max_inline_per_pr: 0.5`, passed with `--targets`, fails the `mock-ok` run on comments per PR; (d) precision rows say "not enough data" below `min_findings`; (e) the `test_gate_*` tests pass; (f) a gate failure shows in CI as a red step.
- **Partial:** (b) passes on smoke, but `test_gate_fails_a_significant_drop_and_passes_a_tie` shows the gate blocks drops on larger sets, and the limitation is documented. **Fail:** neither (b) nor that test shows a blocked regression.
- **Watch:** the baseline catches only 5 fixtures, and a two-sided exact McNemar test on 5 vs 0 gives p = 0.0625, so the smoke gate may pass a reviewer that finds nothing.

**G2 · CI workflows** · W2
- **Pass:** `evals.yml` parses (`yaml.safe_load`, plus `actionlint` if installed). The `test` job runs pytest and `validate`. Without `REVIEWER_REPO_TOKEN`, `smoke` skips and prints its note; with it, `smoke` runs run, score and gate (RUN1 reproduces this locally). `manual` runs only on `workflow_dispatch` and uploads artifacts. Permissions are `contents: read`. On GitHub, the latest push to main shows green `test` (evals) and `reviewer` (prototype `ci.yml`) jobs.
- **Partial:** the workflows are correct but have never run green on GitHub (for example, because they weren't pushed). **Fail:** a syntax error, or a red `test` job.
- **Key later:** a `workflow_dispatch` run on `dry-run` with the Bedrock secret, and the smoke job with `REVIEWER_REPO_TOKEN` set.

### Robustness

**R1 · Reviewer failures are recorded, not fatal** · W3
- **Pass:** using the mock, one run per mode, each with its own `--out`. Each run finishes all 13 cases, writes logs to `runs/_work/mock/` and records the matching row: `crash` → `error: exit 1: mock: crashed on purpose`; `hang` with `--timeout 5` → `timeout` (the run still ends within about a minute); `garbage` → `error: bad output: …`; `noout` → `error: exit 0: …`. `score` on these files reports the errors without crashing.
- **Partial:** one mode is mislabeled. **Fail:** a run aborts the batch, or hangs past its timeout. **Evidence:** the status lines, and one log per mode.

**R2 · Resume and retry** · W2
- **Pass:** start `MOCK_MODE=slow uv run evals run --reviewer mock --set smoke --runs 3 --out $T/resume.jsonl`, press Ctrl-C after about 10 rows, and re-run it. The second run says "N runs to do (M already in …)". The final file parses and has exactly 39 rows, and `jq -r '[.case_id,.run]|@tsv' $T/resume.jsonl | sort | uniq -d` prints nothing. After a `crash` run, `MOCK_MODE=ok … --retry-errors` redoes only the failed pairs.
- **Partial:** it resumes, but a torn last line needed manual repair. **Fail:** duplicates, lost rows, or successful runs redone.

**R3 · Bad input and offline** · W2
- **Pass:** each of these gives a one-line message and a nonzero exit, never a traceback: an unknown `--reviewer` or `--set` (the message lists the valid names); `score` on a missing file; a scratch case with bad YAML or a mismatched id (`validate` names the file); a scratch non-fixture case with no SHAs (`error: prepare: missing base/head/merge_base`); `run --reviewer diff-only` without a key ("calls Bedrock … use blast-radius-rules"). With the network off, RUN1 still passes, and `--set dry-run --limit 2` with the mock records `error: prepare: …` rows without crashing.
- **Partial:** 1–2 tracebacks. **Fail:** 3 or more, or offline runs crash the batch.

### Prototype reviewer

**P1 · The prototype runs offline** · W3 · **MP**
- **Pass:** `make run FIXTURE=signature LLM=0` reports the 2 callers in `app/bulk_send.py` that don't match the new `get_customer` signature. `make run FIXTURE=rounding BEDROCK=fake` replays `tests/transcripts/rounding.json` and gives the undercharging finding on `app/pricing.py`. `make query CALLERS=segment_count` and `make index` work, and nothing is posted.
- **Partial:** one command needs a workaround. **Fail:** rules mode or fake-model mode doesn't give its finding.
- **Evidence:** excerpts of both reviews. **Key later:** `make doctor` all ✅, then `make run FIXTURE=rounding` live.

**P2 · Rules-mode accuracy on the 13 fixtures** · W2
- **Pass:** in RUN1's `score` output (or `make eval LLM=0`), each rule fixture (contract, yaml-config, signature, rename-ts, hostile) is caught inline. The clean fixtures (hub, clean-refactor, move-function) get 0 inline findings, no behavior fixture gets a wrong inline rule finding, and collision doesn't flag `digest.py`.
- **Partial:** one miss. **Fail:** 2 or more misses, or any inline finding on a clean fixture. **Key later:** model mode with 3 runs: does it still meet the published 10/10?

**P3 · Prototype safety and failure messages** · W2
- **Pass:** all five hold:
  - (a) `make run FIXTURE=hostile LLM=0` leaks nothing: list the branch's symlinks and targets (`git ls-tree -r origin/fixture/hostile`), then grep the output and `run-log.json` for the targets' contents.
  - (b) `make run FIXTURE=nope LLM=0` exits nonzero and gives the problem, cause and fix (like `failure.json`).
  - (c) `make doctor` without credentials names the missing credential and the fix.
  - (d) `ai-review.yml` triggers only on comments starting `@bandwidth-reviewer` from an OWNER, MEMBER or COLLABORATOR; checks out the default branch with `persist-credentials: false`; never builds or runs PR code; and honors the `BLAST_RADIUS_ENABLED` kill switch.
  - (e) without `--post` and with `GITHUB_TOKEN` unset, a run makes no GitHub calls.
- **Partial:** one of (b)–(e) fails. **Fail:** (a) leaks, or PR code is checked out or run. **Key later:** a real review posted on a fixture PR, following the README's browser setup.

### Docs

**D1 · README and RUNBOOK are accurate** · W2
- **Pass:** `evals <cmd> --help` accepts every command and flag in the README table and RUNBOOK steps 0–8 (check, for example, `prepare --source traced`, `judge-audit export -n 40`, `categorize --export-sample 50` and `run --retry-errors --timeout`). The RUNBOOK troubleshooting rows match what R1 and R3 produced. Paths the docs name exist or are created on first use (`labels/`, `results/…/README.md`). Relative links resolve. A newcomer can find the no-key path (rules-only smoke) from the README.
- **Partial:** 2–4 mismatches. **Fail:** 5 or more, or a step that can't work as written. **Evidence:** each mismatch with its file and line.

**D2 · The reviewer contract is enough to build `bwr`** · W2
- **Pass:** the JSON example in `docs/reviewer-contract.md` validates: save it as `ex.json`, then run `uv run python -c "import json,sys; from bandwidth_evals.contract import ReviewOutput; print(ReviewOutput.model_validate(json.load(open(sys.argv[1]))))" ex.json`. Every field and enum in the doc's tables appears in `contract.py`, and the reverse holds. RUN2 and R1 confirmed rules 3 (exit 0 on partial) and 4 (unknown fields ignored). The Appendix A mock, written only from the doc, worked.
- **Partial:** 1–2 fields drift between the doc and the code, or between the doc and spec Appendix A (the `info` severity). **Fail:** the example doesn't validate.

### Spec & plan

**S1 · The spec is complete and testable** · W2
- **How:** fill a table that maps each item below to the plan §6 test or the measurement that checks it: each §2 goal and success metric (its numeric target and "measured by"); each §3.2 command (a defined reply or §3.5 error row); each §10 threat (its control and test); each §13 deliverable (concrete or not); each §14 question (a day-1 owner or not).
- **Pass:** at least 90% of the threats and metrics map to a test or measurement. **Partial:** 70–89%. **Fail:** under 70%. **Evidence:** the table, with gaps marked.

**S2 · The plan is feasible and sequenced** · W2
- **Pass:** every task has an owner, and every day ends with an observable check. Day 1 has a go/no-go with a defined no-go path and a no-go definition of done. The cut list never cuts safety or the eval gate. Each §7 definition-of-done item maps to a scheduled task. Nobody security-reviews their own code. The eval order holds: judge trusted (day 3), calibrate (day 4), freeze (day 5), holdout (day 6), no tuning after.
- **Partial:** 1–2 definition-of-done items have no task. **Fail:** 3 or more, or a sequencing contradiction. **Evidence:** a table mapping each definition-of-done item to its day and task.

**S3 · Spec, plan, eval repo and prototype agree** · W2
- **How:** mark each item *consistent*, *fixed*, *documented gap* or *undocumented gap*:
  1. `evals calibrate` (spec §11.5, plan day 4) exists in `--help`.
  2. `gate.py` and `targets.yml` enforce the v1 precision rule from spec §2: ≥0.80 *and* a Wilson lower bound ≥0.70 over at least 30 findings.
  3. Clean-PR noise ≤0.1 per PR (spec §2, plan §7) is a gate target. Today `targets.yml` has only `max_inline_per_pr: 4`.
  4. Smoke covers "all agents, replayed model calls" (spec §11.2, eval-plan §6). Today CI runs blast-radius rules-only, and `bwr` is `needs_model: true`.
  5. The prototype's test count: 68 in the README, 69 in the spec and plan.
  6. Severity enums: the contract has `info`, spec Appendix A doesn't.
  7. Judge trust in spec §11.3 (≥90% over at least 20 rows) matches `judge.py`.
  8. "479+ cases" (plan §1) and the README counts match `stats`.
  9. The links from the spec and `eval-design.md` into the eval repo resolve on GitHub `main`.
- **Pass:** 0 undocumented gaps. **Partial:** 1–3. **Fail:** 4 or more.

### Handoff readiness

**H1 · Committed, pushed, and works from a fresh clone** · W3 · **MP**
- **Pass:** in all three repos, `git status --short` and `git log origin/main..main` are both empty, and U1, U2, RUN1 and P1 pass from the GitHub clones alone.
- **Partial:** the clones work, but some docs or results exist only locally. **Fail:** any graded code or config exists only locally.
- **Watch:** on Nov 4, the evals repo's `RUNBOOK.md`, `docs/reviewer-contract.md`, `reviewers.yml`, `eval-sets.yml`, `targets.yml`, `baselines/`, `.github/workflows/evals.yml`, 13 `src` modules and 2 test files were untracked. So were the spec and plan in `bandwidth-code-reviewer`.

**H2 · Portable and transferable** · W2
- **Pass:** `git grep -nE '/Users/|/home/'` finds no personal paths in any repo (line 1 of `production-spec.md`, for example, holds a local autoplan path). A transfer checklist lists the owner-specific references (`rishyendra333/…` in `evals.yml` and doc links). The docs cover the sibling-folder layout and the `BLAST_RADIUS_DIR` and `BWR_REVIEWER_CMD` overrides. Data licenses are stated (SWE-PRBench CC BY 4.0 with attribution, Qodo MIT). Each `results/` folder has a README naming the model, reviewer commit and set. Documented commands recreate the ignored data (`data/raw`, `data/mirrors`, `runs/`).
- **Partial:** 1–2 misses. **Fail:** 3 or more.

### Security hygiene

**SEC1 · No secrets in any repo or its history** · W3 · **MP**
- **Pass:** in all three repos, `git log -p --all | grep -nE 'bedrock-api-key-[A-Za-z0-9]|(AKIA|ASIA)[0-9A-Z]{16}|ghp_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{20,}|xox[abp]-[0-9]|sk_live_[0-9A-Za-z]{10,}|BEGIN [A-Z ]*PRIVATE KEY|aws_secret_access_key *='` finds nothing but documented placeholders, each explained (`--all` covers the `fixture/*` branches). `gitleaks detect --log-opts=--all` is clean, if gitleaks is installed. `git status --short --ignored` shows no credential file waiting to be committed.
- **Partial:** only placeholder hits that aren't documented. **Fail:** any real-looking credential in a tracked file or in history. This caps the grade at 40.

**SEC2 · Keys come from the environment only, and synthetic secrets stay synthetic** · W2
- **Pass:** `git grep -nE 'AWS_BEARER_TOKEN_BEDROCK|AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|GH_TOKEN'` shows only environment reads, `${{ secrets.* }}`, and docs that say `export` (never "write it in a file"). No config file has a credential field. `.gitignore` covers `.env`, `runs/` (its logs hold rebuilt synthetic secrets), `run-log.json` and `failure.json`. `results/` and `baselines/` pass the SEC1 grep. `AWS_BEARER_TOKEN_BEDROCK=dummy-not-a-key uv run evals doctor --live` doesn't print the value. Workflows grant least privilege.
- **Partial:** one miss (for example, `.env` isn't ignored). **Fail:** a doc or tool asks for a key in a file, or prints a key.

## Scoring

- **Points:** Pass = 1, Partial = 0.5, Fail = 0. A verdict without its required evidence counts as Fail. N/T leaves the criterion out of the denominator. A report with more than 6 weight points of N/T is incomplete and goes back to the tester.
- **Grade:** 100 × Σ(weight × points) ÷ Σ(weight of the criteria tested). The total weight is 66.
- **Must-pass caps:** if SEC1 fails, the grade is at most 40. If another must-pass (U2, RUN1, P1, H1) fails, it's at most 59. If any must-pass is Partial, it's at most 79.
- **Bands:** 90–100 means ready to hand off. 80–89 means ready after the listed, non-blocking fixes. 60–79 means not ready: fix before Nov 13. Under 60 is blocking.
- **Deferred (key):** list key-only checks separately, each with its exact command. They don't change the grade; they're day-1 work for whoever gets Bedrock access.

## How to report

Each tester writes one `$T/evidence/report.md` and saves full logs as `$T/evidence/<ID>.log`. Never paste a token, even a dummy one.

```text
Tester: <name> · Date: <YYYY-MM-DD> · Machine: <OS>, python <v>, uv <v>, git <v> · GitHub login: yes/no
Commits: evals <sha> (clone|copy) · blast-radius-demo <sha> (clone|copy) · bandwidth-code-reviewer <sha>
No-key proof: env | grep -cE '^(AWS_|EVAL_)'  ->  0

### <ID> · <Pass | Partial | Fail | N/T>
Evidence:
  $ <command>
  exit: <code>
  <at most 20 lines of output, or "see evidence/<ID>.log">
Notes: <what differed from the criterion; repro steps for any failure; why N/T>
Deferred (key): <exact command, or "none">

Summary: | ID | Verdict | W | Points |   (one row per criterion, then the grade with any cap applied)
```

## Appendix A: mock reviewer

Save this as `$T/mock_bwr.py`. It stands in for `bwr review` and writes canned `bwr.review/v1` JSON.

```python
#!/usr/bin/env python3
"""Stand-in for `bwr review`: writes canned bwr.review/v1 JSON. MOCK_MODE picks the behavior."""
import json, os, sys, time
args = sys.argv[1:]
out = args[args.index("--out") + 1]
run = int(out.rsplit("--", 1)[-1].split(".")[0])            # the runner names files <case>--<run>.json
mode = os.environ.get("MOCK_MODE", "ok")
if mode == "crash": sys.exit("mock: crashed on purpose")
if mode == "hang": time.sleep(3600)
if mode == "slow": time.sleep(2)
if mode == "noout": sys.exit(0)
if mode == "garbage": open(out, "w").write("{not json"); sys.exit(0)
finding = {"id": "BR-1", "agent": "blast-radius", "rule": "blast-radius/behavior", "severity": "high",
           "confidence": 0.9, "file": "app/pricing.py", "line": 12, "symbol": "segment_count",
           "affected": ["app/pricing.py:30 message_cost"], "title": "segment_count change breaks message_cost",
           "body": "mock", "evidence": ["app/pricing.py:12"], "placement": "inline", "not_in_contract": True}
keep = {"empty": False, "once": run == 0, "twice": run in (0, 1)}.get(mode, True)
agents = [{"name": "blast-radius", "status": "ok"}]
if mode == "partial": agents.append({"name": "tests", "status": "error", "error": "mock failure"})
json.dump({"schema": "bwr.review/v1", "reviewer": "mock", "status": "partial" if mode == "partial" else "ok",
           "seconds": 0.1, "cost_usd": 0, "agents": agents, "findings": [finding] if keep else [],
           "dropped": [], "extra_top_level": 1}, open(out, "w"))
```

Run `export MOCK_BWR=$T/mock_bwr.py`, add this entry to the scratch clone's `reviewers.yml`, and revert the file when you're done:

```yaml
mock:
  cmd: >-
    python3 ${MOCK_BWR} review --repo-path {repo} --base {base} --head {head} --merge-base {merge_base}
    --agents={agents} --title={title} --out {out}
  output: contract
  needs_model: false
```
