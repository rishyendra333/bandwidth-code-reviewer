# Production Spec and Plan — Review Record

Nov 4, 2026 · Reviews [production-spec.md](production-spec.md) and [production-plan.md](production-plan.md) · Method: `/autoplan` (strategy, engineering, developer-experience and security reviews, with auto-decisions). The Codex CLI isn't installed, so each phase used one independent Claude reviewer (`[subagent-only]`); the consensus tables below therefore show one voice. The design review phase was folded into the developer-experience review, because the product's only UI is GitHub comments and checks.

**History:** earlier drafts of this file reviewed the Oct 22 drafts of the spec (first blast-radius-only, then multi-agent). Both were superseded by this version; the restore point for this round is in `~/.gstack/projects/rishyendra333-bandwidth-code-reviewer/`.

## Premise gate (answered by the user)

All six premises hold, with four changes from the user:

| # | Premise | Result |
| --- | --- | --- |
| 1 | The full reviewer: 5 agents, single or combined, comment-triggered only, inline comments, never blocks or rewrites | Holds |
| 2 | Own everything on Bandwidth's AWS account with Bedrock | Holds |
| 3 | Lambda per agent behind Step Functions; own agent SDK on Converse; AgentCore as the upgrade path | Holds |
| 4 | Tree-sitter knowledge in v1; SCIP later | Holds |
| 5 | Team of 5, one agent plus one platform piece each | Holds. **Changed:** the deadline is next week (Nov 13), "fully doable with AI" |
| 6 | Eval pipeline as the release gate | Holds. **Changed:** there is no Bandwidth holdout set; the holdout comes from our own repos |
| — | Infrastructure as code | **Changed:** Terraform instead of CDK |
| — | Presentation | **Changed:** rethink the 👀/🚀 reactions and how the bot presents itself |

All four changes were applied before the reviewers ran (spec 3.3, 4.5, 11.2; plan rewritten for a 7-day schedule with a handoff demo).

## Primary review

### What already exists

| Sub-problem | Existing code | Reused as |
| --- | --- | --- |
| Code graph, change detection, impact walk, contracts | `blast-radius-demo/.github/bandwidth-reviewer/blast_radius/graph`, `changes.py`, `impact.py`, `contracts.py` | `bwr_knowledge` |
| Agent loop with budgets, forced finish, record/replay | `blast_radius/agent/loop.py`, `bedrock.py`, `tools.py` | `bwr_sdk` |
| Deterministic checks, aggregation, rendering | `checks.py`, `aggregate.py`, `render.py` | Starting point for `bwr_pipeline` and the blast-radius agent |
| Message catalog, config schema, command grammar | [spec.md](spec.md), [implementation-plan.md](implementation-plan.md), `messages.py`, `commands.py` | `bwr_core` |
| Bedrock API key auth for accounts without IAM users | `demo-repo` (commit `a62e32d`) | The fallback when IAM roles can't be created |
| Eval harness, cases, judge, scorer | `bandwidth-reviewer-evals` | The release gate |

### Not in scope (v1, Nov 13)

| Item | Why it's deferred |
| --- | --- |
| Automatic reviews on PR open | The product is comment-triggered by decision |
| Shadow-mode automation and daily shadow reports | v1 switches agent versions by hand with AppConfig; automation is in the backlog |
| Fargate indexing for very large repos | v1 indexes in Lambda; repos over the limit get summary-only blast radius |
| SCIP, cross-repo contracts, AgentCore, RL fine-tuning | Upgrades taken only when evals show the need |
| 10x load test and a full chaos suite | v1 runs four chaos checks |

### Error and rescue registry

| Code path | What can go wrong | Rescue | User sees |
| --- | --- | --- | --- |
| Ingress | Bad signature | Reject 401, no queue | Nothing (not GitHub) |
| Ingress | Duplicate delivery | Conditional write fails → drop | Nothing |
| Dispatcher | No write access | No run | One reply per PR |
| Dispatcher | Same commit, same agents already running or done | No new run | Reply with a link |
| Dispatcher | Quota reached, or kill switch on | No run | Check: reason and reset time |
| Prepare | Fetch fails (force-push, deleted fork) | Retry 2× with backoff, then fail | Check: "Couldn't fetch `abc1234`; it may have been force-pushed. Comment again." |
| Prepare | Bundle over 2 GB, PR over the size limit | Summary-only for the largest files | Summary says what was skipped |
| Agent | Bedrock throttling | Jittered backoff, 3 tries, then unfinished | Agent row: "didn't finish (model busy)" |
| Agent | Malformed model output | One retry with the validation error | Nothing, or "didn't finish" |
| Agent | Refusal, content filter, empty output | Deterministic findings only | Agent row notes it |
| Agent | Timeout (5 min) or crash | Map branch catch; others continue | Agent row: "timed out" |
| Progress | GitHub 5xx on the check update | Ignore (progress is best effort); Post sets the final state | A briefly stale progress line |
| Aggregate | All agents failed | Post a failure summary | Check: "Review didn't run" with reasons |
| Post | 422 on a line | Retry once with those comments moved to the summary | Fewer inline comments; summary has the rest |
| Post | GitHub 5xx, or timeout after the review was created | Retry; the run-ID marker prevents a duplicate | One review |
| Post | Head moved during the run | Post only findings whose lines still exist | Note naming the reviewed commit |
| Feedback | Reaction fetch rate-limited | Back off; retry next hour | Nothing |

### Failure modes registry

| Failure | Detection | Impact | Covered in |
| --- | --- | --- | --- |
| An agent becomes noisy after a release | Dismiss-rate alarm; live audit | Bot gets muted | Kill switch per agent; eval gate; rollback (spec 11.6, 12) |
| Model invents files or lines | Evidence verification (stage 2) | Wrong comments | Spec 8, stage 2; `unverified_evidence` counted in evals |
| Concurrent requests on one PR | Run claim per head SHA and agent set | Duplicate reviews | Spec 4.3, step 2 |
| Prompt injection asks the model to stay silent | Injection cases in every eval set; deterministic findings can't be suppressed | Missed issues | Spec 10 |
| Graph stale or missing | Index lag alarm; reduced-mode note | Weaker blast radius | Spec 6, 12 |
| AWS account can't create IAM roles | Day-1 check | Blocks deploy | Plan, section 9 |

### Test coverage map

Each new code path, and what tests it (plan section 6):

| Code path | Test type | Status in plan |
| --- | --- | --- |
| Command parsing, aliases, unknown names | Unit | Planned, day 1 |
| Router (explicit, default, disabled, not applicable) | Unit | Planned, day 2 |
| Each pipeline stage, with drop reasons | Unit | Planned, day 2 |
| Renderer templates | Snapshot | Planned, day 2 |
| Agent candidates and runs | Unit + recorded model | Planned, days 1–2 |
| Contract output, for every agent | Contract test + `evals validate` | Planned |
| Check-run progress from parallel branches | Integration (dev stack) | Planned, day 3 |
| Idempotent post, 422 retry, head moved | Integration with recorded payloads | Planned, days 3–5 |
| Chaos: crash, throttle, 502, token expiry | Fault injection | Planned, day 5 |
| Injection and secrets never in output | Eval cases + unit | Planned, day 5 |
| Terraform | fmt, validate, Checkov, plan | Planned, day 1 onward |

## Independent reviews (round 1, on v2)

Four reviewers, each independent and without access to the others or to this record. Every finding below was applied in v3 unless it appears under "Your choices".

### Consensus (single voice per phase; Codex unavailable)

| Dimension | Strategy | Engineering | DX | Security |
| --- | --- | --- | --- | --- |
| Premises and scope sound? | Partly: integration came too late; dependencies unchecked | — | — | — |
| Architecture sound? | — | No: dispatch not idempotent, Map fails whole, tokens and network contradict the spec | — | No: "no network" and "own run prefix" not enforced |
| Error paths handled? | — | No: no finalizer, claims never freed, 422 retry unbuildable | Partly: failures invisible to people who aren't watching the checks | — |
| Security covered? | Partly: "no network access" false | No: tokens in state; the judge can drop deterministic findings | — | No: no repo scoping, no install allowlist, self-silencing, secrets sent to the model |
| Presentation right? | Partly: the demo uses our own fixture | — | Partly: no notifications from checks, threads block merges | — |
| Plan realistic? | Not as written: needs a go/no-go, a thin slice, and correct eval ordering | Labeling 100 per agent by day 4 is unrealistic | — | — |

**Cross-phase themes** (raised independently by two or more reviewers, so high confidence):
- **Agents aren't actually network-isolated.** Strategy, engineering and security reviewers all flagged it. → A no-NAT VPC with endpoints, presigned URLs, and an outbound test.
- **The judge can drop deterministic findings.** Engineering and security. → Demote-only, with demotions counted.
- **Tokens and the private key are spread across functions, and tokens end up in Step Functions history.** Engineering and security. → A Token broker with a KMS sign-only key; repo-scoped tokens; IDs only in state.
- **Retention misses several stores.** Engineering and security. → Every store listed with its retention.
- **`dismiss` has no permission rules.** Engineering, DX and security. → Write access required; PR authors can't dismiss security findings on their own PRs; wrong vs wontfix.
- **The demo uses our planted fixture.** Strategy and DX. → A real regression traced back to the PR that caused it, plus a clean-PR moment and a closed loop.
- **Events and controls that weren't subscribed.** Engineering and DX. → `check_run.rerequested`, `pull_request_review_thread`, `installation_repositories`.

### Strategy (CEO) findings → decisions

| Finding | Severity | Decision |
| --- | --- | --- |
| The deploy relies on IAM role creation, which is already blocked for IAM users | Critical | Day-1 5pm go/no-go; the GitHub Actions demo path if no-go; Terraform handed over plan-verified and labeled that way |
| Integration happens last (day 3) | Critical | Day-2 thin slice: blast radius end to end on the real path |
| Unplanned scope (self-hosted pricing API, learn PRs, reaction sync, quotas, prod apply, 7 docs) | High | Dollar figures to backlog; `learn` replies instead of opening PRs; reactions read when the PR closes; quotas kept (security needs them); prod apply behind approval; 5 docs |
| Eval ordering spoils the holdout | High | Judge checked on day 3; code freeze at end of day 5; holdout on day 6; no tuning after it |
| Precision gate needs 100 findings per agent; DoD contradicts the risk table | High | v1: ≥ 30 judged findings with Wilson lower bound ≥ 0.70; default set = agents that pass; GA keeps 100 |
| B and E overloaded; B reviews his own security | Medium | A runs the security pass; D helps E label |
| No cost or quota estimate for benchmarks | Medium | Day-1 estimate from `dry-run`; baselines 1 run |
| github.com vs Enterprise Server, compliance, languages, eval repo ownership | High/Medium | Day-1 questions; `SECURITY.md` on day 2; v1 scoped to two languages; eval repo transferred at handoff |
| Six-month regret: nobody at Bandwidth can maintain it | Critical | A named owner is a precondition of the transfer; recorded walkthroughs; rehearsed model upgrade; humans approve every prompt, manifest, pipeline and infra change |
| Adoption: people forget a comment-only bot; one wrong finding kills trust | High | Pilot team, champion and a 30-day pilot as the demo's ask; v1 default = security + blast-radius only |
| Demo: planted fixture, no clean-PR moment, no ask | High | Rebuilt (plan section 8) |

### Engineering findings → decisions

| Finding | Severity | Decision |
| --- | --- | --- |
| Dispatch isn't idempotent; claims never freed; delivery recorded before enqueue | Critical | `run_id` from the delivery ID; a claim state machine with TTL; `StartExecution(name=run_id)`; Finalizer on EventBridge; record delivery after `SendMessage` |
| "No network beyond Bedrock" is false; Semgrep metrics and registry; Infracost calls out | Critical | No-NAT VPC + endpoints; Semgrep offline; Infracost out of v1 |
| Token holders contradict 4.1; tokens in execution history | High | Token broker; repo- and permission-scoped tokens; IDs only in state |
| Progress race; inline Map fails as a whole | High | Catch inside the iteration; sequence-numbered progress renders |
| The 422 retry can't be built as written | High | `commit_id` = reviewed SHA; pre-validated anchors; bisect, then summary-only; files without patches are summary-only |
| A single image conflicts with independent releases | High | Per-agent image digests; versions plus `live`/`shadow` aliases; rollback = alias shift |
| The judge can drop deterministic findings; suggestions are a payload | High | Demote-only; payload lint |
| Bedrock IAM for geographic profiles; Lambda concurrency quota | High | Profile + foundation-model ARNs; quotas on day 1 |
| Prepare: merge base, fork heads, token in URL, bundle size | Medium | Compare API merge base; `refs/pull/N/head`; header-only token; per-SHA tree cache; 4 GB ephemeral storage |
| Missing events | Medium | All subscribed (spec 4) |
| `dismiss` permissions; `resolveReviewThread` needs node IDs | Medium | Permission rules; a GraphQL `reviewThreads` lookup; day-1 spike |
| Permission fallbacks can't happen (all-or-nothing install) | Medium | Removed: no `contents: write` at all (learn replies); no "can't create checks" fallback |
| Terraform: AppConfig values reverted by apply; plan runs provider code; manifest validation; ARN passing; lock-file version | Medium | Flags not managed by Terraform; read-only plan role, no fork plans; JSON Schema; `templatefile` + `jsonencode`; Terraform ≥ 1.11 |
| Retention misses stores | Medium | Data store table (spec 10) |
| Cold start vs the 5 s acknowledgment; rebase fallback; `review security` superseding a full review | Medium | Slim Dispatcher image with provisioned concurrency 1; full review after a rebase; supersede only for the same agent set |
| Test-plan gaps | — | Added (plan section 6) |

### Developer-experience findings → decisions

| Finding | Severity | Decision |
| --- | --- | --- |
| Check-run updates send no notifications; failures go unseen; triggers outside the Conversation tab are undefined | Critical | A status comment under the trigger, edited in place, with older ones hidden (see choice 1); triggers accepted in review bodies and threads |
| Bot threads block merges under "require conversation resolution" | Critical | Auto-resolve the bot's fixed threads; documented in INSTALL |
| The check's Re-run does nothing | High | `rerequested` handled; "Retry failed agents" and "Run all agents" buttons |
| Feedback channels overlap and contaminate evals | High | `dismiss wrong` vs `wontfix`; resolving a thread means acknowledged, not correct |
| Severity unexplained; default set inconsistent | High | Severity legend; the default set rule in section 2 |
| The tests agent will be the noisiest | High | At most 1 inline comment; test code in `<details>`; gate includes the pilot 👍 rate |
| Caps hide critical findings | High | Critical and high exempt; unanchored highs listed visibly |
| Demo undersells | High | Rebuilt (plan section 8) |
| Progress counts shown before filtering | Medium | Progress shows state only |
| Email and mobile rendering; repeated footers; the `learn` nag | Medium | Rows only for agents with findings; versions in the summary only; short footer; `learn` reminder once per repo |
| Mention typos, handle squatting, no `cancel`, undefined partial commands | Medium | Near-miss replies; reserved handle; `cancel`; partial-unknown and `review all` rules |
| Config can't be tested before merge | Medium | The summary validates the PR's version of the config |
| Two agents, same line, different issues | Medium | One comment with sections |
| Inconsistencies (quota reply vs check; ignore-marker syntax) | Medium | Fixed |

### Security findings → decisions

| Finding | Likelihood/impact | Decision |
| --- | --- | --- |
| Self-silencing: ignore markers, judge persuasion, size-cap evasion | High/High | Markers count only if present at the merge base; demote-only judge; scanners run on every changed file |
| Who can `dismiss` | Medium/High | Write access; PR authors can't dismiss security findings on their own PRs; dismissals listed |
| Path traversal, `/tmp` reuse, shared agent S3 access | Low-Medium/Critical | Path confinement; `/tmp` wiped; presigned URLs only (agents have no S3 permissions) |
| Suggestions and pasted tests as payloads | Medium/High | Payload lint |
| Spam through URLs and references | Medium/Low | Structured rendering with escaping |
| Budget exhaustion; ReDoS; `rg` argument injection | Medium/Medium | Quotas per user, repo and org; RE2; pure-Python tools, no subprocesses |
| Learner runs a model over untrusted text while holding credentials | Medium/High | Model step without credentials; no write permission at all |
| Tokens not repo-scoped; private key spread; no install allowlist; webhook hardening; tokens in history or traces | Medium/Critical | Token broker + KMS; `repository_ids`; private App with allowlist; constant-time check first, throttling, two secrets; IDs only in state |
| Secrets sent to Bedrock and logs | High/High | Masking before any model call |
| Unlisted data stores; operator access; eval repo on a personal account | High/High | Data-store table; prompt logs off by default with break-glass; eval repo transferred |
| Infracost isn't static; parser exploits reach the internet; supply chain; CI/CD and OIDC | Medium/High–Critical | Infracost out of v1; VPC; pinning, hashes and digests; SHA-pinned Actions; scoped OIDC; CODEOWNERS |

## Round 2 (on v3)

A fresh reviewer read both v3 documents for contradictions and remaining critical gaps. All 15 findings were applied:

| # | Finding | Severity | Decision |
| --- | --- | --- | --- |
| 1 | Presigned URLs still need an S3 route from a no-NAT VPC; Aggregate needs S3 and DynamoDB; agents can't call Progress | Critical | S3 and DynamoDB gateway endpoints with pinned policies; Progress is its own Map state |
| 2 | Ingress kept only commands, dropping indexing, feedback and install events | High | Routed by type: a command queue and an events queue |
| 3 | No permissions table; Prepare's token can't read PR metadata; org config conflicts with repo-scoped tokens | High | Permissions, events and per-caller token scopes table (spec 4.2); org-wide defaults to the backlog |
| 4 | Incremental reviews plus auto-resolve would mark untouched findings "Fixed"; `--full` had two meanings | High | Every review analyzes the whole PR; only new fingerprints post; resolve only for agents that ran; `--full` bypasses the already-reviewed check |
| 5 | The Token broker can't identify callers; Prepare parses PR code with internet access | High | One broker alias per caller, scope from the invoked alias; parsing moved into the VPC (Fetch outside, Prepare inside) |
| 6 | Three sources for the default set; defaults decided before the holdout; "≥ 0.80" hides the real bar | Medium | The default set is an AppConfig flag (repo config narrows it), flipped after the holdout; the bar stated as 26/30 (27/30 for security) |
| 7 | The security pass reviews the reviewer's own code; the fresh install is run by its builder; no cut order | Medium | D runs the security pass (A reviews D); E runs INSTALL; an ordered cut list |
| 8 | The no-go path didn't say how Actions reaches Bedrock; no no-go DoD; fresh-account quota traps | Medium | Bedrock API key secret for Actions; a no-go DoD; fresh env = new env in the same account; `bwr doctor` pre-flight |
| 9 | DNS exfiltration and endpoint credential misuse | Medium | DNS Firewall allowlist; endpoint policies pin accounts; DNS in the outbound test |
| 10 | Bedrock invocation logging is account-level | Medium | Day-1 question and a `bwr doctor` check |
| 11 | Reserving the user handle may block the App name; the dev trigger differs | Medium | Day-1 spike; trigger handle per environment |
| 12 | `ExecutionAlreadyExists`; duplicate status comment after a crash; the post marker conflicts with the no-HTML rule; late Progress overwrites the Finalizer | Low–Med | Treated as success; a hidden marker, exempt from the rule; the Finalizer writes a terminal sequence number |
| 13 | Payload lint bans imports that generated tests need | Low–Med | Repo modules and the test framework allowed |
| 14 | Retention: logs and Step Functions history can't be purged per repo; noncurrent versions; prompt logs had no write path; purge and cleanup missing from the plan | Low–Med | Stated plainly; noncurrent expiry on every bucket; a prompt-log PUT URL when enabled; purge and cleanup scheduled (day 5) |
| 15 | Terraform path and key bugs; image wording; CLI flag mismatch; bloat | Low | Path fixed, keyed by name, image wording clarified, flags reconciled; decision tables moved to appendix C |

**Checked and correct** (from round 2):
- KMS can import RSA key material for sign-only keys.
- Check runs allow up to 3 requested-action buttons, with labels of 20 characters or fewer.
- GraphQL `resolveReviewThread` and `minimizeComment` work with installation tokens that have `pull_requests: write`.

## Decision audit trail

| # | Phase | Decision | Class | Principle | Rejected |
| --- | --- | --- | --- | --- | --- |
| 1 | Premise | All six premises hold; Terraform, no Bandwidth holdout, rethought presentation, next-week deadline | User | — | — |
| 2 | Strategy | Day-1 go/no-go with one fallback path | Mechanical | P6 | Building two delivery paths |
| 3 | Strategy | Day-2 thin slice | Mechanical | P1 | Integrate on day 3 |
| 4 | Strategy | Cut dollar cost estimates from v1 | Taste (choice 4) | P3 | Self-hosted pricing API in v1 |
| 5 | Strategy | `learn` replies with the proposed file | Taste (choice 3) | P5 | Bot opens PRs (needs `contents: write`) |
| 6 | Strategy | Default set = agents that pass their gate; security + blast-radius expected | Taste (choice 2) | P1 | All five default |
| 7 | Strategy | Eval ordering: judge check → calibrate → freeze → holdout | Mechanical | P1 | — |
| 8 | Strategy | Named Bandwidth owner as a transfer precondition | Mechanical | P1 | — |
| 9 | Strategy | Demo rebuilt around a real regression, a clean PR, a closed loop and an ask | Mechanical | P1 | Planted fixture |
| 10 | Eng | Idempotent dispatch, Finalizer, claim states | Mechanical | P1 | — |
| 11 | Eng | No-NAT VPC for agents and Aggregate | Mechanical | P1 | Claim without enforcement |
| 12 | Eng | Token broker with a KMS sign-only key | Mechanical | P5 | Secrets Manager key with several readers |
| 13 | Eng | Sequence-numbered progress; Catch inside the Map | Mechanical | P5 | — |
| 14 | Eng | 422: reviewed SHA, pre-validation, bisect | Mechanical | P3 | Remap to the new head |
| 15 | Eng | Per-agent image digests and aliases | Mechanical | P1 | One image for all |
| 16 | Eng | Demote-only judge for deterministic findings | Mechanical | P1 | — |
| 17 | Eng | AppConfig flag values outside Terraform; read-only plan role; Terraform ≥ 1.11 | Mechanical | P5 | — |
| 18 | DX | Status comment + check run, no reactions | Taste (choice 1) | P1 | Reactions; check only |
| 19 | DX | Auto-resolve fixed threads; Re-run; `cancel`; `dismiss wrong`/`wontfix` | Mechanical | P1 | — |
| 20 | DX | Tests agent capped at 1 inline | Mechanical | P5 | 4 inline |
| 21 | DX | High findings exempt from caps | Mechanical | P1 | — |
| 22 | Security | Ignore markers from the merge base only | Mechanical | P1 | — |
| 23 | Security | Secret masking before models | Mechanical | P1 | — |
| 24 | Security | Payload lint; structured rendering with escaping | Mechanical | P1 | — |
| 25 | Security | Prompt logs off by default; break-glass access | Mechanical | P1 | On by default |
| 26 | Security | Eval repo transferred to Bandwidth before any of their data goes in | Mechanical | P1 | — |
| 27 | Evals | Holdout from our own repos (by repo hash); seven holdout repos mined | Mechanical | P1 | Waiting for Bandwidth data |

## Your choices (taste decisions)

1. **How the bot acknowledges a request.** I chose a status comment under the trigger, edited in place, plus the check run, with no reactions, because you said reactions aren't ideal. The DX reviewer recommended keeping a 👀 reaction instead of the comment: it sends no notifications and shows on mobile. The cost of my choice is one notification per request.
2. **Default agents at handoff.** I chose only agents that pass their release gate, with security and blast-radius expected. Making all five default shows more, but risks a noisy first week (tests is the likely offender).
3. **`learn`.** I chose to have it reply with the proposed `conventions.md` for the team to commit. Opening a PR is smoother, but needs `contents: write` (or a second App) and a credentialed write path.
4. **Dollar cost estimates.** I moved them to the backlog; v1 reports resource-level changes. Keeping dollars in v1 needs a self-hosted, network-isolated Infracost pricing service.
