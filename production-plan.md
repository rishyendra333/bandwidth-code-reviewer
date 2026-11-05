# Bandwidth AI Code Reviewer — Production Implementation Plan

Nov 4, 2026 · Status: v3, revised after /autoplan · Spec: [production-spec.md](production-spec.md) · Evals: [bandwidth-reviewer-evals](https://github.com/rishyendra333/bandwidth-reviewer-evals) · **Handoff: Fri Nov 13, 2026**

## What we're building

A deployed, measured v1 of the full reviewer, handed to Bandwidth on Nov 13. That's 7 working days for a team of 5, each running Claude Code sessions in parallel. v1 is:
- one private GitHub App
- one Terraform-managed AWS stack
- five agents, each in its own Lambda
- the shared findings pipeline
- the eval pipeline as the release gate

## How the plan stays on track

AI does most of the typing, so the plan is built around what AI can't speed up:

| What AI can't speed up | How the plan handles it |
| --- | --- |
| **Outside dependencies:** AWS permissions, Bedrock quotas, Bandwidth's answers | All start on day 1, with a go/no-go at the end of the day |
| **Integration** | A thin end-to-end slice exists by day 2, and every other piece plugs into it |
| **Honest measurement** | The judge is checked against people before it's used, the code freezes before the holdout runs, and nothing is tuned after the holdout |

## 1. What we start from

| Piece | Exists today | Becomes |
| --- | --- | --- |
| Blast-radius prototype (`blast-radius-demo/.github/bandwidth-reviewer`) | Tree-sitter graph, change detection, impact walk, deterministic checks, a Converse loop (budgets, forced finish, record/replay), renderer, 69 tests, `--merge-base`. Caught 10/10 on fixtures | `bwr_knowledge`, `bwr_sdk` and `agents/blast_radius` |
| Per-agent prototypes (GitHub Actions, Oct 5–23) | One per agent | Ported into `agents/<name>/` |
| First-mock plan ([implementation-plan.md](implementation-plan.md)) | Message catalog, config schema, command grammar | Carried over into `bwr_core` |
| Eval pipeline (`bandwidth-reviewer-evals`) | Contract v1, runner over real PRs, baselines (diff-only, grep agent), judge plus human audit, model-based sorting, gate, validate, CI, RUNBOOK; 479+ cases with SHAs and merge bases prepared | The release gate from day 2 |

## 2. Repo layout (`bandwidth-reviewer`, a uv workspace)

```text
bandwidth-reviewer/
  packages/
    bwr_core/        # Finding, ReviewContext, AgentManifest (+ JSON Schema), bwr.review/v1, config schema, command parser
    bwr_sdk/         # Converse loop, judge/verify, confined read-only tools (RE2), secret masking, caching, record/replay
    bwr_knowledge/   # tree-sitter graph, tests map, repo profile, contracts, conventions store, S3 cache
    bwr_pipeline/    # prepare, router, findings pipeline (stages 1–11), payload lint, render, progress, post, feedback
    bwr_github/      # token-broker client, REST + GraphQL client, webhook verification, near-miss mention matching
  agents/
    security/  tests/  conventions/  blast_radius/  infra/   # manifest.yaml, prompt.md, agent.py, rules/, tests/, eval.yaml, README.md
    _template/                                              # copied by `bwr new-agent`
  functions/         # ingress, dispatcher, events, token_broker, fetch, prepare, agent, progress, aggregate, post, finalizer, index, learner, feedback, cleanup, purge
  cli/               # bwr review | render | new-agent | doctor   (eval mode = production code path, writes the contract)
  infra/             # Terraform modules (network, ingress, github, pipeline, agent, knowledge, data, observability, flags) + envs/dev, envs/prod
  docs/              # README, INSTALL, ADDING-AN-AGENT, RUNBOOK, SECURITY
  .github/           # CODEOWNERS; workflows: ci.yml (lint, types, tests, smoke evals, terraform fmt/validate/plan, Checkov),
                     # deploy.yml (images → ECR by digest, apply dev; prod behind approval; OIDC, actions pinned to SHAs)
```

**Stack:**
- **Language and tooling:** Python 3.12, `uv` (lockfile with hashes), Powertools, `boto3`, `githubkit`, `pydantic` v2
- **Parsing and scanning:** `tree-sitter-language-pack` (pinned), `google-re2`, `python-hcl2`, gitleaks, Semgrep (pinned, offline rules)
- **Testing and checks:** `pytest`, `respx`, `moto`, `ruff`, `mypy`
- **Infrastructure:** Terraform ≥ 1.11, Checkov

**Images:**
- one slim image for the Dispatcher and the Token broker
- one platform image
- one agent image, with a per-agent digest so each agent releases on its own

## 3. Owners

The workload is rebalanced so nobody security-reviews their own code, nobody checks their own install docs, and the eval owner has help with labeling.

| Person | Agent | Platform workstream |
| --- | --- | --- |
| A | blast-radius | Agent SDK, knowledge layer, Fetch and Prepare; reviews D's findings-pipeline code on day 5 |
| B | security | GitHub App, Ingress, Dispatcher, Token broker, status comment and check run UX, commands |
| C | tests | Terraform (network/VPC, all modules, envs), Step Functions, Finalizer, images, deploy workflow, AppConfig |
| D | conventions | Findings pipeline, payload lint, renderer, Post, feedback, learner; **runs the security pass on day 5** (D wrote none of the ingress, broker, SDK, Prepare or network code); helps E label the judge sample |
| E | infra | Eval pipeline, benchmarks, calibration, dashboards and alarms, runbooks, the handoff demo; **runs the fresh-environment INSTALL check on day 6** (E didn't build the deploy) |

**Working rules:**
- `bwr_core` interfaces are frozen at the end of day 1. Any change after that goes through a PR that all five owners review.
- Each person runs 2–3 Claude Code sessions in parallel, each on separate files and a separate branch.
- **A human reads and approves every merged change** to prompts, manifests, the findings pipeline and `infra/`. CODEOWNERS enforces this.
- An agent merges only with its tests and an eval run attached to the PR.
- 9am, 15 minutes daily: yesterday's end-of-day check, blockers, today's owners.

## 4. Schedule

### Day 1 · Thu Nov 5 · Dependencies, contracts, spikes

| Task | Owner |
| --- | --- |
| **Outside dependencies, first thing:**<br>• Can Terraform create IAM roles in the team AWS account? If not, request a sandbox account from Bandwidth.<br>• Request Bedrock tokens-per-minute and Lambda concurrency quotas.<br>• Ask Bandwidth the spec's section 14 questions: github.com or Enterprise Server, top 2 languages, compliance review, a named owner and pilot team | C, B |
| **Spikes (1 hour each):**<br>• Import an RSA key into KMS (`EXTERNAL`, RSA_2048, sign-only) and sign a GitHub App JWT with `kms:Sign`.<br>• Call `resolveReviewThread` and `minimizeComment` with an installation token.<br>• Mint a token scoped with `repository_ids` + `permissions`.<br>• From a Lambda in a no-NAT VPC: call `bedrock-runtime` through its endpoint, use a presigned S3 GET and PUT through the S3 gateway endpoint, and confirm a public DNS lookup fails under DNS Firewall.<br>• Check whether reserving the user handle `bandwidth-reviewer` blocks naming the App; decide the trigger handle per environment | B, C |
| Create the repo, workspace, CI and CODEOWNERS | C |
| `bwr_core`: schemas, manifest JSON Schema, contract v1 (matching the eval repo's `docs/reviewer-contract.md`), config schema, command parser (aliases, near-miss mentions, `dismiss wrong`/`wontfix`, `cancel`) | B, D |
| Extract `bwr_sdk` and `bwr_knowledge` from the prototype, keeping its 69 tests green. Add path confinement, RE2 and secret masking | A |
| Port each agent prototype into `agents/<name>/`, with `default: false` | All |
| Evals: run `evals categorize`, then a person checks 50 items. Estimate benchmark cost and throughput from the `dry-run` set. Finish mining the holdout repos | E |

**5pm go/no-go on the deploy path:**
- **Go:** Terraform can deploy in an account we control, so days 2–7 follow this plan.
- **No-go:** the demo path becomes the same `bwr` package running in GitHub Actions on sandbox repos, the way the prototypes ran.
  - It reaches Bedrock with a Bedrock API key stored as the `AWS_BEARER_TOKEN_BEDROCK` repo secret, so no IAM roles are needed.
  - Terraform is handed over as "verified with `plan`, not applied", and the handoff says so plainly.
  - There is no second delivery path, and the no-go definition of done in section 7 applies.

**End-of-day check:**
- `bwr review --agents blast-radius` on the fixtures writes a valid contract.
- All four spikes have answers.
- The go/no-go is decided.

### Day 2 · Fri Nov 6 · A thin slice, end to end

| Task | Owner |
| --- | --- |
| **The thin slice:** the blast-radius agent alone, from comment to posted review, on the real deploy path. That means Ingress → Dispatcher (status comment) → Step Functions → Fetch → Prepare → one agent → Progress → Aggregate (stages 1, 2, 7, 11 only) → Post | B, C, A, D |
| Terraform: `network` (with S3/DynamoDB gateway endpoints and DNS Firewall), `data`, `ingress`, `github`, `pipeline` and one `agent` instance, in dev | C |
| Every other agent: candidates → judge → verify locally, with recorded-model tests | All |
| Send a `SECURITY.md` draft (threat model and data handling, from spec section 10) to Bandwidth | B |
| Evals: first `regression` runs per agent, with `bwr` × 3 runs and the baselines × 1 run | E |

**End-of-day check:**
- Commenting `@bandwidth-reviewer review blast-radius` on a sandbox PR gets a status comment within 5 seconds, then a posted review.
- The first per-agent eval table is published.

**Weekend, Nov 7–8:** buffer, plus overnight benchmark runs (E starts them; unattended).

### Day 3 · Mon Nov 9 · All agents in the pipe

| Task | Owner |
| --- | --- |
| The rest of the agents plug into the Map, with their own aliases and image digests | C, all |
| Progress λ (sequence-numbered updates), Finalizer λ, run claims with state and TTL, `cancel`, the check's Re-run and requested actions | B, C |
| Findings pipeline: all 11 stages, including grouping, caps with the high-severity exemption, and payload lint; snapshot-tested templates | D |
| Index job on default-branch push, the tree cache, tests map, and repo profile with the auth pattern | A |
| **Judge check:** D and E label the judge sample with `evals judge-audit`. The judge is trusted only at ≥ 90% agreement; otherwise, fix the rubric and re-check | D, E |

**End-of-day check:**
- `review`, `review security`, `review all`, `cancel`, the check's Re-run and `status` all work on the dev stack.
- The judge is trusted.

### Day 4 · Tue Nov 10 · Quality and calibration

| Task | Owner |
| --- | --- |
| `evals calibrate --split dev` with the trusted judge; thresholds written into each manifest and reviewed. Calibration and tuning use only the dev and test splits; the holdout stays untouched until day 6 | E, all |
| Tune each agent on its `regression` failures (dev and test splits only), then **re-run `evals calibrate --split dev` on the tuned version** so thresholds match what ships at the day-5 freeze | All |
| `dismiss` (reply and resolve), auto-resolving fixed threads, superseded summaries, feedback on PR close | D |
| Learner with no credentials; `learn` replies with the proposed `conventions.md` | D |
| Dashboards and alarms | E |

**End-of-day check:** each agent's `regression` gate result is known, and gaps are written up. The default set is not decided yet; that happens after the holdout run on day 6.

### Day 5 · Wed Nov 11 · Hardening, then code freeze

| Task | Owner |
| --- | --- |
| **Security pass** (by D, who wrote none of the security-critical code; A reviews D's pipeline code): `/cso` on the repo plus a manual check against spec section 10. Must show:<br>• outbound HTTP and DNS from an agent fail<br>• IAM-negative tests pass (an agent can't read secrets, and has no S3 access beyond its presigned URLs)<br>• each broker alias can mint only its own scope<br>• injection cases are in every agent's set<br>• Checkov is clean | D (A reviews D) |
| **Chaos and failure checks:**<br>• the Dispatcher crashes at each step and SQS redelivers<br>• an execution times out or is aborted (the Finalizer handles it)<br>• an agent crashes<br>• Bedrock throttles<br>• GitHub returns 502 on post<br>• a token expires mid-run<br>• a 422 contract test against real GitHub (bisect path) | C, B |
| Quotas (user, repo, org), the installation allowlist, kill switches, the full error catalog; the scheduled cleanup and purge functions; `bwr doctor` pre-flight (quotas, first-use form, invocation logging off, concurrency) | B, C |
| **End of day: code freeze.** After this, only bug fixes go in, each reviewed by two people | All |

**End-of-day check:** 50 consecutive sandbox runs, including pushes and force-pushes during a review, with no duplicate reviews, no stuck claims and no unhandled 422s.

### Day 6 · Thu Nov 12 · Holdout, pilot, docs

| Task | Owner |
| --- | --- |
| **Holdout run:** the `release` set on the frozen code, published as-is. **No tuning after this.** Agents that pass are added to the AppConfig default set | E |
| Pilot: everyone reviews real PRs on team sandbox repos and an active open-source fork. Bugs are fixed; prompts are not tuned | All |
| Docs: README, INSTALL, ADDING-AN-AGENT, RUNBOOK (including model upgrade and key rotation), SECURITY | All |
| A fresh environment (a new env in the same account) from scratch, following only INSTALL.md and `bwr doctor` | E |
| **Model-upgrade rehearsal:** switch one agent to another model, re-run calibration and the gate, and move the alias | E, A |
| Each owner records a 20-minute walkthrough of their area | All |
| Find a real regression for the demo. Trace a fix in Bandwidth's public repos (for example their SDKs) back to the PR that caused it, and check the reviewer catches it there. Fallback: a real open-source PR in their stack | E, A |
| Demo rehearsal and a recorded backup | All |

**End-of-day check:** someone who didn't build the deploy gets a first review from a fresh environment using only `INSTALL.md`.

### Day 7 · Fri Nov 13 · Handoff

The demo (section 8) and the handoff meeting. Deploy into Bandwidth's account if access was granted. Transfer both repos to Bandwidth's org. Agree on the pilot.

**Precondition:** a named Bandwidth owning team. Without one, the handoff is a demo, not a transfer, and the docs say so.

**If the schedule slips, cut in this order:**
1. The learner (ship conventions as opt-in with a hand-written file)
2. Coverage ingestion for tests
3. CDK resource diffs in infra
4. Near-miss mention replies
5. Superseded-summary edits
6. The check's requested-action buttons (keep Re-run)

Never cut evidence verification, network isolation, token scoping, idempotent dispatch or the eval gate.

## 5. In v1, and in Bandwidth's backlog

| In v1 (Nov 13) | Backlog (documented in the repo) |
| --- | --- |
| Five agents, single or combined; judge with demote-only power over deterministic findings; verify; calibrated thresholds | Daily shadow comparison reports (v1: shadow aliases plus a manual comparison) |
| Status comment and check run, grouping, payload lint, the error catalog, Re-run, `cancel`, auto-resolve | Dollar cost estimates (a network-isolated, self-hosted Infracost pricing API) |
| Tree-sitter knowledge with the tree cache, tests map, repo profile; the learner replies with proposed conventions | Fargate indexing for very large repos; SCIP; cross-repo contracts; AgentCore |
| No-NAT VPC for agents, KMS sign-only App key, repo-scoped tokens, private App with an allowlist | A 10x load test |
| Terraform dev + prod; OIDC; Checkov; CODEOWNERS; alarms; dashboards; kill switches; alias rollback | RL fine-tuning (spec appendix B) |
| Eval pipeline: smoke in CI, regression gate, trusted judge, holdout report | Live-audit automation |

## 6. Test plan

| Layer | What's tested | How | When |
| --- | --- | --- | --- |
| Unit | Command parser (aliases, near-misses, partial unknowns), router, config, each pipeline stage, payload lint, fingerprints, renderer (snapshots), token scoping, signature check (including base64 bodies) | pytest | Every commit |
| Agent | `candidates()`, `run()` with recorded replies, injection fixtures, path-confinement attempts (`../`, `/proc`) | pytest + record/replay | Every commit |
| Contract | Every agent's output validates as `bwr.review/v1` and is readable by the eval runner | pytest + `evals validate` | Every commit |
| State machine | The ASL definition, Map Catch paths, result selectors | Step Functions `TestState` API | Infra PRs |
| Smoke eval | All agents on the fixtures, replayed | `evals run --set smoke` in CI | Every commit |
| Regression eval | Changed agents on the test split, live, 3 runs, then the gate | `evals run` + `evals gate` | Prompt, model, rule, filter or knowledge PRs |
| Infrastructure | `fmt`, `validate`, Checkov, read-only `plan`; manifest schema | CI | Infra and manifest PRs |
| Integration | Recorded webhook payloads: redelivery, out-of-order events, push and force-push during a review, PR closed mid-run, fork PRs, renames, files without patches, comments on deleted lines | Dev stack | Days 3–6 |
| Failure | The Dispatcher crash matrix; Finalizer on abort and timeout; concurrent Progress ordering; agent crash; Bedrock throttling; GitHub 502; token expiry; a 422 bisect against real GitHub | Fault-injection flags + real GitHub | Day 5 |
| Security | Outbound traffic from agents fails; agents can't read secrets or S3; secrets never appear in comments, logs, X-Ray or Step Functions history | Tests + `/cso` + manual review | Day 5 |
| Capacity | Bedrock tokens-per-minute at 5 agents × 5 concurrent reviews | Script against dev | Day 5 |
| Supply chain | `uv.lock` has hashes; base images pinned by digest; every Action pinned to a SHA; scanner and grammar versions pinned | CI check script | Every commit |
| Data retention | Every bucket has lifecycle rules (including noncurrent versions) and every log group has retention; the purge deletes all versions of a test repo's objects and its DynamoDB items | Terraform plan assertions + a purge test in dev | Day 5 |
| Operator access | Normal roles are denied on the prompt-log bucket; only the break-glass role can read it, and CloudTrail records it | IAM-negative test in dev | Day 5 |
| Audit | A review, a command, a dismissal and a config change each write an audit record with the actor and run ID | Integration test | Day 5 |
| Deploy | `terraform apply` and `destroy` in a fresh account | C | Day 6 |

## 7. Definition of done (Nov 13)

- [ ] On the deployed stack, all of these work: `review`, `review <agent>`, `review all`, `cancel`, `status`, `help`, `learn`, `dismiss wrong`/`dismiss wontfix`, and the check's Re-run.
- [ ] A status comment appears within 5 seconds and shows per-agent progress, and failures are always visible there.
- [ ] Agents that pass their release gate are in the default set; the rest are opt-in, with the gap written up. Results, holdout numbers and baselines are published.
- [ ] Clean-PR noise is at most 0.1 comments per PR for the default set, and every posted comment has verified evidence.
- [ ] 50 consecutive runs, including pushes during a review: one review each, no stuck claims, no unhandled 422s.
- [ ] Agents can't reach the internet, DNS or GitHub, and reach S3 only through this run's presigned URLs. Tokens never reach a model, log or execution history. Tests prove all of it.
- [ ] Any agent can be paused or rolled back (alias shift) in seconds.
- [ ] Someone outside the deploy work gets a first review from a fresh environment using only `INSTALL.md`.
- [ ] The model-upgrade procedure has been rehearsed once.
- [ ] A named Bandwidth owner, a pilot team and pilot dates are agreed, or their absence is written down.

**No-go version** (if the day-1 deploy check fails):
- The same commands and agents work in GitHub Actions on sandbox repos.
- `terraform plan` succeeds for dev and prod.
- All eval results are published.
- The handoff states that the AWS stack hasn't been applied yet, and lists what Bandwidth must provide to apply it.

## 8. The handoff demo (about 15 minutes)

1. **Trigger at minute 0.** Comment `@bandwidth-reviewer review` on the demo PR right away, so the review runs while you talk.
2. **The problem (2 min).** A real regression: a fix in Bandwidth's public code (or a real open-source PR in their stack), traced back to the PR that caused it. "This shipped. Here's what the reviewer said about the PR that caused it."
3. **The result (3 min).** The status comment ticks through the agents, and the review lands:
   - one grouped comment with the broken callers, permalinks and a suggestion
   - apply the suggestion with one click
   - re-review, and the bot's thread resolves itself with "Fixed in …"
4. **Judgment, not just pattern matching (2 min).** `review security` on a PR with a real-looking key *and* an obvious test fixture. The bot flags the key, and correctly treats the fixture as a question or ignores it.
5. **Quiet when it should be (1 min).** A clean PR comes back "No issues found" in one line.
6. **Feedback (1 min).** `dismiss wontfix` on a tests finding: the bot acknowledges it and resolves the thread.
7. **Why trust it (3 min).**
   - the eval table: each agent against the diff-only and grep baselines, on public benchmarks and our holdout
   - precision, recall, clean-PR noise, cost per review
   - the finding that diff-only reviewers make up files, and evidence verification removes those comments
   - the pilot's 👍 rate so far
8. **How it runs (1 min).** One diagram; flip a kill switch.
9. **The ask (2 min).** A named owner, 3 pilot repos, a 30-day pilot with dates, and the success metrics from spec section 2.

**Backup:** a recorded run of steps 3–6.

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| The team AWS account can't create IAM roles | High | Blocks the deployed stack | Day-1 go/no-go; the GitHub Actions demo path; Terraform handed over plan-verified, and labeled that way |
| Bedrock or Lambda quotas too low | Medium | Throttled reviews and benchmarks | Requested on day 1; baselines run once; `dry-run` first |
| An agent misses its gate | Medium | That agent ships opt-in | The default set is only agents that passed; per-agent kill switch |
| Public eval sets don't match Bandwidth's code | High | Tuned for the wrong code | Holdout from repos we never tune on; results labeled "indicative" |
| Bandwidth's compliance review takes weeks | Medium | Pilot delayed | `SECURITY.md` sent on day 2; the pilot starts on sandbox repos |
| No named owner at Bandwidth | Medium | The tool is abandoned after handoff | Required for the transfer; walkthroughs, runbooks and a rehearsed model upgrade |
| Seven days is tight | High | Rough edges, or a missing feature | Thin slice on day 2; code freeze on day 5; the ordered cut list in day 7; a clear backlog |
| Tree-sitter name collisions in large repos | Medium | Blast-radius false positives | Edge confidence, verify, collision fixtures; SCIP in the backlog |
