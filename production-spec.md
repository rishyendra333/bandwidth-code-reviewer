# Bandwidth AI Code Reviewer — Production Spec

Nov 4, 2026 · Status: v3, revised after /autoplan with strategy, engineering, developer-experience and security reviews (record: [production-spec-review.md](production-spec-review.md)) · Plan: [production-plan.md](production-plan.md) · Evals: [bandwidth-reviewer-evals](https://github.com/rishyendra333/bandwidth-reviewer-evals) ([reviewer contract](https://github.com/rishyendra333/bandwidth-reviewer-evals/blob/main/docs/reviewer-contract.md)) · Background: [spec.md](spec.md), [agent-setup.md](agent-setup.md)

## 1. Summary

**What it is:** a GitHub App that runs in Bandwidth's AWS account. When someone comments `@bandwidth-reviewer review` on a pull request, it runs specialist review agents and posts **one review with inline comments**. The five agents are:
- security
- tests
- conventions
- blast-radius
- infra (performance and cost)

**Modular agents:**
- Each agent is a self-contained module running as its own Lambda function, with its own version.
- A user can call one agent (`@bandwidth-reviewer review security`) or several.
- Each agent can be built, evaluated, released, paused and rolled back on its own.

**Code knowledge:** agents get knowledge prepared ahead of time (a code graph, a tests map, a repo profile, learned conventions), plus read-only tools.

**One coherent review:** a shared findings pipeline turns the agents' output into one review. It:
- checks every finding's evidence
- filters out weak findings
- groups related findings
- formats the comments

**What Bandwidth owns:** everything. The code, prompts, infrastructure (Terraform) and eval data are theirs, and the models run through Amazon Bedrock in their own account. No third-party review service is involved.

## 2. Goals, non-goals, success metrics

**Goals**

1. One comment gets one review in a few minutes, containing only issues worth a human's attention.
2. Any agent runs alone or with others, and is developed and released independently.
3. Every comment cites evidence that exists in the repo, and says what's wrong, why it matters and how to fix it.
4. Every agent is measured by the eval pipeline before it ships, and its thresholds come from those measurements.
5. It deploys into Bandwidth's AWS account from one Terraform configuration, and one owning team operates it.

**Non-goals**

- Approving, blocking or rewriting PRs. The bot posts `COMMENT` reviews and a check that is never red.
- Running automatically on every PR. Reviews start only from a comment, or from the check's Re-run button. Other events are used only for indexing and feedback.
- Running, building or testing PR code.
- Replacing linters, formatters or CI.

**Success metrics.** Eval targets live in the eval repo's `targets.yml`.

| Metric | v1 target (handoff) | GA target (after the pilot) | Measured by |
| --- | --- | --- | --- |
| Precision per agent | Observed precision ≥ 0.80 (security ≥ 0.90) **and** a Wilson lower bound ≥ 0.70, over at least 30 judged findings. At 30 findings, that means 26/30 correct (27/30 for security) | Same, with at least 100 judged findings (79/100; security 90/100) | Eval benchmark, then a monthly live audit |
| Recall per agent | Reported per agent | Floor set from the pilot | Eval sources with complete answer keys |
| Comments on clean PRs | ≤ 0.1 per PR across all default agents | Same | Eval clean sets, live |
| Useful-comment rate | Reported from the pilot | ≥ 70% 👍, or the commented code changed in a later commit | Live feedback |
| Acknowledgment | Status comment within 5 s | Same | Run records |
| Latency, comment to review | p50 < 3 min, p95 < 8 min | Same | Run records |
| Cost per review | Measured in the first benchmark; starting target median < $0.25 | Reset from pilot data | Bedrock usage per run |
| Reliability | ≥ 99% of requests end in a review or a clear failure message | Same | Run records, the finalizer |

**Default agents.**
- The default set (what a bare `review` runs) is an AppConfig flag. A repo's config can narrow it.
- An agent joins the default set only after it passes the `release` (holdout) gate. That gate runs on the frozen code, so the set is decided at the end of the plan, not during tuning.
- Until then the agent is opt-in, and `review tests` always works.
- The expectation for v1 is that **security and blast-radius** start in the default set.

## 3. User experience

### 3.1 Install

1. A Bandwidth org admin installs the **private** GitHub App on chosen repos. It can only be installed in Bandwidth's org, and the service rejects any installation that isn't on its allowlist. `INSTALL.md` lists every permission and states that code only goes to Bandwidth's AWS account.
2. Nothing is posted on install. Background setup runs per repo: the code index, the repo profile, and the convention learner's first pass. `@bandwidth-reviewer status` shows how far setup has gotten.
3. **Optional config:** `.github/bandwidth-reviewer.yml` on the default branch (section 9). Org-wide config defaults are in the backlog, because each token is scoped to one repo.
4. **Repos that require resolved conversations:** in these repos, bot threads count toward the rule. The bot resolves its own threads when the code is fixed (3.4), and anyone can resolve the rest. `INSTALL.md` explains this.
5. **Trigger handle:** set per environment: `@bandwidth-reviewer` in prod, `@bandwidth-reviewer-dev` in dev. On day 1, a spike checks whether to reserve the plain user handle (so nobody else receives the mentions) without blocking the App's own name.

### 3.2 Commands

A command is read from the first line of:
- a Conversation comment
- a review body
- an inline review-thread reply

Only people with write access can run commands.

| Command | What it does |
| --- | --- |
| `@bandwidth-reviewer review` | Runs the default agents that apply to this PR |
| `@bandwidth-reviewer review security` | Runs one agent |
| `@bandwidth-reviewer review security tests` | Runs the named agents. Unknown names are reported, and the valid ones still run |
| `@bandwidth-reviewer review all` | Runs every enabled agent, including opt-in ones. On a commit that was already reviewed, it runs only the agents that haven't run yet |
| `@bandwidth-reviewer review --full` | Reviews again even if this commit and these agents were already reviewed. Every review analyzes the whole PR; only findings not already posted, resolved or dismissed are posted |
| `@bandwidth-reviewer cancel` | Stops the running review for this PR |
| `@bandwidth-reviewer status` | Setup status, config in effect (and the PR's config change, validated), agent versions, last review |
| `@bandwidth-reviewer learn` | Re-learns conventions, then replies with the proposed `conventions.md` for the team to commit |
| `@bandwidth-reviewer help` | Commands, agents, the severity legend, config reference, how to report a problem |
| `@bandwidth-reviewer dismiss wrong [reason]` | Reply on a finding: it's a false positive. It isn't posted again in this repo until the code changes |
| `@bandwidth-reviewer dismiss wontfix [reason]` | Reply on a finding: it's correct, but the team accepts it. It's suppressed the same way, and evals don't count it as a false positive |

**Agent names and aliases:**

| Agent | Aliases |
| --- | --- |
| `security` | |
| `tests` | `test-gaps` |
| `conventions` | `style` |
| `blast-radius` | `impact` |
| `infra` | `perf`, `cost` |

**Dismiss rules:**
- Dismissing needs write access.
- A PR's author can't dismiss **security** findings on their own PR.
- Every dismissal is listed in later review summaries for that repo.

**Near-miss mentions** (for example `@bandwidth-review` or `@bandwidthreviewer`) get one reply with the right handle.

**Escape hatches:**
- the `bandwidth-reviewer:skip` label
- `ignore_paths` in config
- `enabled: false` per agent
- an ignore marker: `bandwidth-reviewer: ignore[<agent>]` in a code comment on the line, in that file's comment syntax. A marker is honored only if it already existed at the merge base, so a PR can't silence its own findings.

**Severity legend** (shown in `help` and linked from every summary):

| Severity | Meaning |
| --- | --- |
| **Critical** | A live secret, or exploitable now |
| **High** | Will fail or be insecure for real inputs |
| **Medium** | Likely wrong; depends on inputs the bot can't see |
| **Low** | Worth knowing; summary only |

### 3.3 How the bot shows it's working

The prototypes reacted with 👀 and 🚀. Reactions are vague: they don't say which agents are running, how long it will take or what failed, and they're easy to miss.

The bot instead replies right away with **one status comment** under the trigger and edits it as the review progresses. The **check run** carries the same status, plus the Re-run button.

| Moment | Status comment (edited in place) | Check run |
| --- | --- | --- |
| Within 5 s | "Reviewing `abc1234` with security, blast-radius. Usually about 3 min." | In progress, with the same text |
| As agents finish | "security ✓ · blast-radius running" (state only; counts appear after filtering) | Same |
| Done | "Review posted: 1 high, 2 medium → [review](…)" or "No issues found by security, blast-radius" | Completed (`success` or `neutral`), linking to the review |
| Couldn't start | One sentence on what happened and what to do (no access, unknown agent, quota, already reviewed) | Not created |
| Failed partway | "Review didn't finish: <reason> (run `r-8f2c`). Agents that finished were posted. Re-run from the check, or comment again." | `neutral`, with the same text and "Retry failed agents" |

**Rules:**
- **No reactions.** The status comment is the acknowledgment: it's visible on mobile, in email, and next to the comment the person just wrote.
- **One status comment per request.** When a new request starts, the bot hides its earlier status comments on that PR (minimized as outdated), so the conversation stays clean.
- **Never `failure`.** Checks never look like they block a merge.
- **Re-run controls:**
  - The check's **Re-run** button (`check_run.rerequested`) runs the same agents on the current head.
  - Two buttons appear on the check: "Retry failed agents" and "Run all agents".
- **Re-reviews:**
  - The earlier review's summary is edited to start with "Superseded by the review of `def456`". This happens only when the same agents ran again; `review security` never supersedes a full review.
  - The bot resolves its own threads from the agents that ran, whose finding no longer appears in this full analysis, with a reply: "Fixed in `def456`."
- **`dismiss`:** the bot replies once in the thread ("Got it: marked wrong; this won't be flagged again here unless the code changes") and resolves the thread.

Alternatives considered (reactions only, check run only) are in appendix C.

### 3.4 How comments look

The review should read like one careful senior engineer: few comments, each specific, each with evidence, sorted by importance.

**Grouping:**
- One inline comment per root cause. When one change breaks four callers, the review posts one comment on the changed line with a table of the four callers.
- Two agents, same line, same issue: one comment naming both agents.
- Two agents, same line, different issues: one comment with a section per agent.

**Inline comment template:**

````markdown
**High · Blast radius** — `segment_count` now undercounts segments; 3 callers still expect the old result

`segment_count` switched from rounding up to rounding down (`math.ceil(n / 153)` → `n // 153`). Callers outside this PR:

| Caller | What breaks |
| --- | --- |
| [`send_bulk`](https://github.com/org/repo/blob/abc1234/app/bulk_send.py#L31) | Balance check passes with too little credit |
| [`estimate_handler`](https://github.com/org/repo/blob/abc1234/app/api.py#L19) | Quotes half the real price |
| [`bulk_send_handler`](https://github.com/org/repo/blob/abc1234/app/api.py#L14) | Reports too few segments |

**Example:** a 200-character GSM-7 message is 2 segments; this now returns 1.

```suggestion
    return math.ceil(len(text) / 153)
```

<details><summary>Evidence</summary>

- `app/bulk_send.py:31` `if customer.balance < cost:` (cost comes from `estimate_cost` → `message_cost` → `segment_count`)
- Tests that reach this: `tests/test_pricing.py::test_segment_count` (changed in this PR to expect the new value)
</details>

<sub>👍/👎 · reply `@bandwidth-reviewer dismiss wrong` or `dismiss wontfix`</sub>
````

**Formatting rules.** The renderer enforces these; snapshot tests check them.

1. **Header:** severity word, then agent, then a title of at most 100 characters that states the problem. Severity is always a word, never only an emoji.
2. **Body:** what changed, what breaks and why it matters, in about 120 visible words at most. Everything else goes in a collapsed `<details>` block. Many email clients show `<details>` expanded, so the visible part has to stand on its own.
3. **Evidence:** every file and line reference is a permalink pinned to the reviewed commit.
4. **Concrete example:** required for behavior findings (an input and the wrong result).
5. **Fixes:**
   - A ```` ```suggestion ```` block only when the fix is exact, covers exactly the commented lines, and passes the payload lint (section 8, stage 10).
   - Otherwise, "Possible fix" with a short snippet.
6. **Multi-line comments** (`start_line` to `line`) only when both lines are in the same diff hunk.
7. **Low-confidence findings** that pass the threshold are phrased as questions ("Is this list bounded?").
8. **Footer:** short, and the same on every comment. Versions and rule IDs go only in the review summary.
9. **Never:**
   - restate the diff
   - praise or hedge
   - include @mentions, `#123` or `org/repo#123` references (the renderer's own hidden `<!-- bwr:run=… -->` marker is the one exception to the no-HTML rule)
   - include bare URLs, images or HTML other than `<details>`
   - link outside the repo

**Review summary** (the review's body):

```markdown
## Bandwidth Reviewer · 3 findings on `abc1234` (1 high, 2 medium)

| Agent | Result |
| --- | --- |
| blast-radius | 1 high: `segment_count` breaks 3 callers |
| tests | 2 medium: untested branches in `send_bulk`, `estimate_cost` (see below) |

No issues: security · Not run: infra (no infrastructure changes)

**Not shown inline:** 1 high finding couldn't be placed on a changed line: `app/api.py:88` …   ← highs are always visible

<details><summary>2 more findings, and what this review could not see</summary>
(medium and low findings over the cap; languages without a code index, skipped files, dynamic calls; dismissals in this repo)
</details>

<sub>Reviewed `abc1234` in 2m 41s · security 1.1.0 · tests 0.9.0 · blast-radius 1.2.0 · [what the severities mean](…) · `@bandwidth-reviewer help`</sub>
```

- **Rows** appear only for agents with findings. The rest share one line.
- **Clean result:** a one-line review: "No issues found by security, blast-radius on `abc1234`".
- **Re-reviews:** only new findings are posted. Findings already posted, resolved or dismissed are never repeated.
- **Conventions reminder:** "Conventions not set up yet: `@bandwidth-reviewer learn`" appears once per repo, not on every review.

### 3.5 Error catalog

Every message says what happened, why, and what to do next. "Reply" means a status comment.

| Situation | What the user sees |
| --- | --- |
| Commenter lacks write access | Reply: "Only people with write access to this repo can request reviews." (once per PR) |
| PR closed, or labeled skip | Reply naming the reason |
| Same commit and agents already reviewed | Reply linking to that review; `--full` reviews it again |
| Review already running | Reply: "Already reviewing `abc1234` (started 1 min ago). `@bandwidth-reviewer cancel` stops it." |
| Unknown agent name | The valid names run; the reply adds "I don't know `secuirty`. Did you mean `security`?" |
| An agent failed or timed out | The others post; that agent's line says it didn't finish and why; the check offers "Retry failed agents" |
| Bedrock throttled after retries | Deterministic findings post; the agent line says the model step didn't finish |
| Commit no longer exists (force-push) | Reply: "`abc1234` was force-pushed away; comment again to review the new head." |
| PR too large (over 150 files or 5,000 changed lines) | The largest 150 files are reviewed, and the summary lists the rest. Files GitHub shows without a patch (large, binary, or past file 3,000) are summary-only |
| Setup not finished | Affected agents run in reduced mode; the first line of the review says so |
| Invalid config | Defaults for the bad keys; the summary names the file, line and closest valid key |
| Quota reached (per user, repo or org) | Reply: "Review didn't run: this repo's daily review quota is used; resets 00:00 UTC." |
| Agent paused by the platform team | That agent's line: "Paused by the platform team" |
| Run aborted or timed out internally | The finalizer edits the status comment: "Review didn't finish (run `r-8f2c`)." Nothing half-posted |
| Internal error | "Review didn't run: internal error (run `r-8f2c`). Share the run ID in #bandwidth-reviewer." |

## 4. Architecture

```text
 GitHub ─ webhooks ─► API Gateway (HTTP API, throttled) ─► Ingress λ ─┬─► commands ─► SQS ─► Dispatcher λ ─► Step Functions
                                                                     └─► other events ─► SQS ─► Events λ
                                                                         (push → Index · PR closed / thread resolved → Feedback
                                                                          · installation / installation_repositories → Setup, purge)

 Token broker λ — the only principal allowed kms:Sign on the App key. One alias per caller; the scope comes from
                  the alias that was invoked, never from the request.

 Step Functions (Standard), one execution per review:
   Fetch λ (outside the VPC: talks to GitHub; never parses code)
     merge base from the compare API · PR metadata · fetch base/head/merge base as git objects → raw tree in S3
   Prepare λ (in the VPC; parses untrusted code)
     diff from GitHub patches · tree-sitter overlay on the merge-base graph · config · applies_to per agent
     → tree cache + run bundle in S3 → Map items: agent alias ARN + presigned GET/PUT URLs (15 min)
   Map (inline; a Catch inside each iteration; results = S3 keys only)
     ├─ Agent task: security:live │ tests:live │ conventions:live │ blast-radius:live │ infra:live   (in the VPC)
     │    candidates → judge → verify → bwr.review/v1 → PUT through its presigned URL
     └─ Progress task (outside the VPC): sequence-numbered update of the status comment and check run
   Aggregate λ (in the VPC) — findings pipeline (section 8) → rendered review in S3
   Post λ (outside the VPC) — one review · completes the check · edits the status comment · resolves fixed threads

 Finalizer λ ← EventBridge (execution FAILED / TIMED_OUT / ABORTED): terminal status, neutral check, frees the claim

 VPC (no NAT, no internet gateway): gateway endpoints for S3 and DynamoDB, interface endpoints for bedrock-runtime and
 X-Ray; endpoint policies pinned to our buckets, tables and account; Route 53 Resolver DNS Firewall allows only those
 endpoint names.
```

**What runs where.** Code that parses untrusted PR content (tree-sitter, scanners, the agents, the findings pipeline) runs only inside the VPC, with no route to the internet. Code that talks to GitHub (Fetch, Progress, Post, Dispatcher, Events, Token broker) runs outside the VPC and never parses code.

### 4.1 AWS services

| Need | Service | Why |
| --- | --- | --- |
| Webhook endpoint | API Gateway HTTP API (route throttling) + Ingress Lambda (reserved concurrency) | Answers GitHub within 1 s; cheap |
| Buffers | Two SQS standard queues with DLQs: commands, and other events | Commands are never stuck behind indexing or feedback |
| Orchestration | Step Functions Standard: inline Map, a Catch per iteration, execution name = run ID | Parallel agents with per-branch timeout and retry, visual history, redrive |
| Compute | Lambda (Python 3.12) with Powertools. Agents: one function each, with published versions and `live`/`shadow` aliases | Pay per use at Bandwidth's volume; per-agent IAM, limits, kill switch, logs and release; rollback = alias shift |
| Network isolation | VPC with private subnets, no NAT. Gateway endpoints: S3, DynamoDB. Interface endpoints: `bedrock-runtime`, X-Ray. Endpoint policies pin `aws:ResourceAccount` / `aws:PrincipalAccount` and our bucket and table ARNs. Route 53 DNS Firewall allows only those endpoint names | "Agents can't reach the internet" is enforced by the network, including DNS-based leaks |
| GitHub credentials | The App private key imported into KMS (an `EXTERNAL` RSA_2048 sign-only key); a Token broker Lambda is the only principal with `kms:Sign` | The key can never be read; rotation is a new key plus an alias swap |
| Webhook secret | Secrets Manager (two values during rotation) | Rotation without downtime |
| Models | Bedrock Converse: a Sonnet-class Claude model (agents, verify), a Haiku-class model (screening, classification), via geographic inference profiles | Code stays in Bandwidth's account and geography; prompt caching |
| Run data | S3 with SSE-KMS, versioning, and lifecycle rules on every bucket (noncurrent versions expire in 1 day) | Large blobs between steps |
| State | DynamoDB on demand: deliveries, run claims (state, TTL, check run ID, status comment ID, progress sequence), fingerprints, dismissals, feedback, quotas | Conditional writes for idempotency |
| Runtime flags | AWS AppConfig: kill switches, shadow, **the default agent set**, quotas. Terraform manages the app, environment and profile, never the flag values | Changed in seconds without a deploy; never reverted by `apply` |
| Events and schedules | EventBridge: execution-status rule → Finalizer; Scheduler for the weekly learner, nightly cleanup and purge | |
| Observability | CloudWatch Logs (30-day retention), metrics, dashboards; X-Ray with token-bearing responses never captured; alarms → SNS | One trace per review |
| Images | ECR with immutable tags and scan on push; base images pinned by digest | |
| Infrastructure | Terraform ≥ 1.11 (section 4.5) | Reviewable plans; one module instance per agent from its manifest |

Alternatives that weren't chosen are in appendix C.

**Quotas and account settings to check on day 1:**
- Bedrock tokens-per-minute for both models. The sizing case is 5 agents × 5 concurrent reviews.
- Lambda concurrency. New accounts can start near 10, which makes per-agent reserved concurrency fail at `apply`.
- The Anthropic first-use form in Bedrock.
- Bedrock model invocation logging. It's set per account and Region, so it must be off or limited to metadata. `bwr doctor` checks it.

Agent IAM allows `InvokeModel` on the inference profile *and* on the foundation-model ARNs in every Region the profile routes to.

### 4.2 GitHub App permissions, events and token scopes

**App permissions** (the whole App; an org grants all of them or none):
- Contents: read
- Pull requests: write
- Issues: write
- Checks: write
- Actions: read (coverage artifacts)
- Metadata: read

No `contents: write`: the bot never writes to a repo.

**Webhook events:**

| Event | Used for |
| --- | --- |
| `issue_comment` | Commands on the Conversation tab |
| `pull_request_review` (`submitted`) | Commands in a review body |
| `pull_request_review_comment` | Commands and `dismiss` in review threads |
| `pull_request_review_thread` | Resolution feedback |
| `check_run` (`rerequested`, `requested_action`) | Re-run and retry buttons |
| `pull_request` (`closed`) | Feedback collection |
| `push` (default branch) | Indexing |
| `installation` | Setup, allowlist, purge |
| `installation_repositories` | Setup, allowlist, purge |

**Token scopes per caller.** Every token is minted with `repository_ids=[the PR's repo]`:

| Caller (broker alias) | Permissions on its token |
| --- | --- |
| Dispatcher | pull_requests: read (head SHA, PR state), issues: write (status comment), checks: write |
| Fetch | contents: read, pull_requests: read, actions: read |
| Progress | issues: write, checks: write |
| Post | pull_requests: write, issues: write, checks: write |
| Events (Index, Feedback, Setup) | contents: read, pull_requests: read |
| Learner | pull_requests: read (review history), issues: write (the `learn` reply) |

The broker reads the caller from `context.invoked_function_arn`. Each alias's resource policy allows only its caller's role.

### 4.3 Request flow

1. **Ingress λ:**
   - Verifies `X-Hub-Signature-256` first: over the raw (base64-decoded) body, in constant time, against the current or previous secret.
   - Routes by event type. Command-bearing events (created comments, submitted reviews, check-run buttons) go to the command queue. Everything else goes to the events queue.
   - Drops bots, and comments that are neither a command nor a near-miss mention.
   - Records the delivery ID (7-day TTL) only after `SendMessage` succeeds. Returns `200` and makes no GitHub calls.
2. **Dispatcher λ:**
   1. Sets `run_id` from the delivery ID.
   2. Checks the commenter's permission, parses the command, and applies skip rules, quotas and AppConfig flags.
   3. Claims the run with a conditional write on `repo#pr#head#agentset` (state `dispatching`, TTL).
   4. Posts the status comment with a hidden `<!-- bwr:run=<run_id> -->` marker. On a retry, it first looks for that marker, so a crash never leaves two status comments.
   5. Creates the check run and saves both IDs on the claim.
   6. Calls `StartExecution(name=run_id)`. `ExecutionAlreadyExists` counts as success.
   7. Sets the claim to `running`.
3. **Fetch λ** (token scoped to the repo, with contents and pull requests read):
   - Gets the merge base from the compare API, plus the PR metadata.
   - Fetches base, head and merge base as git objects. Heads of fork PRs come from `refs/pull/N/head`, with the token in a header, never in the remote URL.
   - Writes the raw tree to S3. It never parses code.
4. **Prepare λ** (in the VPC):
   - Builds the diff from GitHub's per-file patches.
   - Loads config from the default branch (and validates the PR's version if it changes the config).
   - Overlays the PR's changes on the merge-base graph.
   - Runs `applies_to` for each agent.
   - Writes the per-SHA tree cache and the run bundle: changed files, diff, context, knowledge slices.
   - Emits one Map item per agent, holding the agent's alias ARN, presigned GET URLs for the bundle and the tree, and a presigned PUT URL for its output.
5. **Map:**
   - **Agent task:** wipes `/tmp`, downloads through its URLs, runs candidates → judge → verify (section 5), and uploads `bwr.review/v1` output, including dropped findings with reasons. A Catch inside the iteration records a failure without failing the Map.
   - **Progress task** (a separate state after the agent): `UpdateItem … ADD seq 1, ReturnValues ALL_NEW` on the run item, then it renders the whole status and edits the status comment and check run. A render with an older sequence number than one already shown is skipped.
6. **Aggregate λ** (in the VPC): runs the findings pipeline (section 8) and renders the review.
7. **Post λ:**
   - Checks for an existing review carrying this run's marker, so a retry never posts twice.
   - Posts with `commit_id` set to the reviewed SHA, using anchors pre-validated against RIGHT-side hunks. On a `422`, it bisects to find the bad anchors and moves them to the summary; failing that, it posts summary-only.
   - Completes the check and edits the status comment.
   - Edits the superseded summary (same agent set only).
   - Resolves the bot's own threads from agents that ran in this review whose fingerprint is absent from this full analysis, with a reply naming the commit. It looks up thread node IDs with GraphQL `reviewThreads`, then calls `resolveReviewThread`.
   - Sets the claim to `done`.
8. **Finalizer λ** (executions that failed, timed out or were aborted): writes a terminal progress sequence number so no late update overwrites it, completes the check as `neutral`, edits the status comment with the run ID, and frees the claim.

**Every review analyzes the whole PR.** Only findings whose fingerprint hasn't already been posted, resolved or dismissed are posted. That's what makes thread auto-resolution safe.

**What Step Functions state holds:** only IDs, S3 keys and presigned URLs that expire in 15 minutes. Never tokens, code or findings (history is kept 90 days).

**Latency budget (p95):**

| Step | Time |
| --- | --- |
| Ingress and dispatch, with the status comment | 5 s |
| Fetch and Prepare (faster when the SHA's tree is cached) | 60 s |
| Agents in parallel (5-minute cap) | 5 min |
| Aggregate and post | 20 s |
| **Total** | **≈ 6.5 min** |

**Dispatcher latency:** it runs on a slim image with provisioned concurrency 1, so the 5-second acknowledgment holds.

### 4.4 Data passed between steps

| Object | Location | Contents | Retention |
| --- | --- | --- | --- |
| Raw tree | `s3://<runs>/raw/<repo>/<sha>.tar.zst` | Fetched files, before parsing | 7 days |
| Tree cache | `s3://<runs>/trees/<repo>/<sha>.tar.zst` | Head-tree text files: no binaries, nothing over 1 MB, no ignored paths, no symlinks | 7 days |
| Run bundle | `s3://<runs>/runs/<run_id>/bundle.tar.zst` | `context.json` (ReviewContext), changed files at base and head, diff, per-agent knowledge slices | 7 days |
| Agent output | `s3://<runs>/runs/<run_id>/agents/<agent>.json` | The `bwr.review/v1` contract. **The eval runner reads the same format** | 30 days |
| Prompt log | `s3://<prompts>/<run_id>/<agent>.json` | Model transcripts, written only when the repo sets `log_prompts: true` (Prepare then issues a second PUT URL) | 30 days, break-glass access |
| Rendered review | `s3://<runs>/runs/<run_id>/review.json` | What was posted, with IDs | 30 days |

Ephemeral storage on Fetch, Prepare and the agents is 4 GB. A tree over 2 GB makes the largest files summary-only.

### 4.5 Infrastructure as code (Terraform)

```text
infra/
  modules/
    network/         # VPC, private subnets (no NAT), S3/DynamoDB gateway + bedrock-runtime/X-Ray interface endpoints, policies, DNS Firewall
    ingress/         # API Gateway HTTP API, Ingress λ, command + event queues and DLQs, Dispatcher λ (provisioned concurrency 1), Events λ
    github/          # Token broker λ and its per-caller aliases, KMS sign-only key, webhook secret container
    pipeline/        # Step Functions (ASL via templatefile), Fetch, Prepare, Progress, Aggregate, Post, Finalizer, EventBridge rule
    agent/           # one agent: Lambda (versions, live/shadow aliases), IAM role (its Bedrock ARNs only), VPC config, alarms
    knowledge/       # Index λ, Learner, cleanup and purge schedules
    data/            # S3 (KMS, versioning, lifecycle incl. noncurrent expiry), DynamoDB, KMS keys, log groups with retention
    observability/   # dashboards, alarms, SNS, budgets
    flags/           # AppConfig application, environment, profile (not the flag values)
  envs/
    dev/   main.tf  terraform.tfvars  backend.tf
    prod/  main.tf  terraform.tfvars  backend.tf
```

**One module instance per agent,** read from the manifests:

```hcl
locals {
  agents_dir = "${path.root}/../../../agents"            # infra/envs/<env> → repo root
  agents = { for f in fileset(local.agents_dir, "*/manifest.yaml") :
             yamldecode(file("${local.agents_dir}/${f}")).name => yamldecode(file("${local.agents_dir}/${f}")) }
}
module "agent" {
  source   = "../../modules/agent"
  for_each = local.agents                                # keyed by agent name ("blast-radius"), not folder
  manifest = each.value
  image    = var.agent_images[each.key]                  # each agent pinned to its own image digest
}
# State machine: templatefile("pipeline.asl.json", { agents = jsonencode({ for k, m in module.agent : k => m.live_alias_arn }) })
```

**Images.** All agents build from one Dockerfile. CI tags an image per agent version and records its digest in `agent_images`. A release changes only the digests of agents that changed, so unchanged agents keep running exactly what they ran before.

**Manifests drive IAM,** so:
- CI validates them against a JSON Schema.
- `CODEOWNERS` requires a platform owner's review for `agents/*/manifest.yaml`, `agents/*/prompt.md`, `infra/` and the findings pipeline.

**State:** an S3 backend per environment, with native lock files (`use_lockfile = true`), encryption and versioning.

**CI** (GitHub Actions, pinned to commit SHAs):

| When | What runs | Role |
| --- | --- | --- |
| PRs from branches in the repo | `fmt`, `validate`, Checkov, `plan` | Read-only OIDC role, `sub` pinned to the repo. Fork PRs never get a `plan`, because `plan` runs provider code |
| Merge | `apply` to dev | Deploy role |
| Prod release | `apply` to prod | Its own role, behind an `environment: prod` approval |

**Secrets never enter state.** Terraform creates the KMS key and the secret containers. An admin imports the App key into KMS and sets the webhook secret once, following `RUNBOOK.md`.

## 5. Modular agents

### 5.1 An agent is a folder

```text
agents/security/
  manifest.yaml      # name, version, owner, applies_to, models, budgets, tools, thresholds, caps
  prompt.md          # system prompt (versioned with the agent)
  agent.py           # applies_to(), candidates(), run()
  rules/             # deterministic checks (pinned Semgrep rules, regexes)
  tests/             # unit tests + recorded-model tests
  eval.yaml          # which eval sets gate this agent, and its targets
  README.md          # what it catches, what it doesn't, known false positives
```

```yaml
# agents/security/manifest.yaml
name: security
version: 1.1.0
owner: "@security-agent-owner"
summary: Hardcoded secrets, SQL built from strings, unsafe deserialization, endpoints missing the repo's auth check
applies_to: {source_files_changed: true}
languages: [python, typescript]   # v1: the two languages Bandwidth names on day 1
models: {judge: sonnet, verify: sonnet, screen: haiku}     # resolved to inference profile ARNs per environment
budgets: {turns: 12, input_tokens: 120000, output_tokens: 8000, seconds: 300}
tools: [read_file, grep, get_diff, get_symbol, get_callers, get_auth_pattern]
knowledge: [repo_profile.auth_pattern]
thresholds: {min_confidence: 0.85}   # from calibration (11.5); repo config can only raise it
max_inline: 4
```

```python
class Agent(Protocol):
    manifest: AgentManifest
    def applies_to(self, ctx: ReviewContext) -> Applicability: ...                    # (bool, reason); plain code
    def candidates(self, ctx: ReviewContext) -> list[Candidate]: ...                  # deterministic; no model
    def run(self, ctx: ReviewContext, cands: list[Candidate], sdk: AgentSDK) -> AgentResult: ...
```

**Rules every agent follows:**
- An agent reads only its bundle, through its tools. It has no GitHub credentials and no internet, and it reaches S3 only through this run's presigned URLs.
- Every finding uses the shared `Finding` schema (appendix A) and cites evidence that exists at the head commit.
- **The model can't drop deterministic findings.** Some candidates skip the judge entirely: secrets in a verified format, removed-but-still-used, and arity mismatches. For other deterministic candidates, the judge may only *demote* a finding (to a question or to the summary). The summary counts how many candidates were demoted.
- An agent may report findings without a deterministic candidate only where its README says so (for example, missing auth, or behavior changes for blast radius). Those findings always go through verify.

### 5.2 Registry and router

- **Registry:** `agents/*/manifest.yaml`, validated in CI. Terraform creates one function per manifest (4.5).
- **Router** (plain code, in the Dispatcher and Prepare) picks the agents in this order:
  1. The agents named in the command (`all` means every enabled agent).
  2. Otherwise, the default set from AppConfig, narrowed by the repo config's `agents.default` if set.
  3. Minus agents disabled in config or paused in AppConfig.
  4. Minus agents whose `applies_to` is false. These are listed as "Not run" with the reason.

  No LLM decides routing.
- **Shadow:**
  - When an agent's AppConfig `shadow` flag is on, Prepare adds a second Map item for that agent's `shadow` alias.
  - Its output is stored, not posted.
  - Promotion moves the `live` alias to the shadow version.

### 5.3 Agent SDK (shared by all agents)

| Piece | What it does |
| --- | --- |
| `sdk.loop()` | Converse tool-use loop: turn, token and time budgets; a forced finish that answers pending tool calls, then asks for `submit_findings`; schema-validated output with one retry; jittered backoff on throttling |
| `sdk.judge(candidates)` | Batched yes/no judgments for simple candidates. It may only confirm or demote deterministic candidates (5.1) |
| `sdk.verify(findings)` | A fresh call that sees only the finding and the cited code, and confirms or rejects it. It stops confident mistakes. It isn't an injection defense, because the cited code is attacker-controlled |
| Tools | Pure Python over the bundle; no subprocesses. Every path is resolved and must stay inside the bundle root. `grep` uses RE2 (linear time, no catastrophic backtracking). Tools: `read_file` (≤ 200 lines), `grep` (≤ 100 hits), `list_dir`, `get_diff`, `get_symbol`, `get_callers(depth)`, `find_references`, `find_tests`, `get_conventions`, `get_auth_pattern`, `get_contract`, `submit_findings`. Results are capped at 8,000 characters |
| Secret masking | Before any text reaches a model, detected secrets are replaced with `<secret:type:first4…>`. The model judges from the type, the context and features such as entropy, never the full value |
| Prompt caching | Cache points after the system prompt and tools, and after the context packet; 1-hour TTL where the model supports it |
| Record and replay | Every model call can be saved and replayed exactly, for tests and the eval smoke tier |
| Telemetry | Tokens, cost, turns, tool calls and timings per agent: as EMF metrics, and in the agent output |

### 5.4 Adding an agent

Target: one afternoon to a first eval run.

1. `bwr new-agent <name>`
2. Fill in `manifest.yaml`, `prompt.md` and `candidates()`.
3. Run it locally: `bwr review --repo-path . --base main --head my-branch --agents <name>`. `--merge-base` is computed when omitted, and `--out` is optional; without it, the rendered review is printed.
4. Add its eval set, then run `evals run --reviewer bwr --set regression --agent <name>`.
5. Open a PR. CI runs the tests, recorded-model tests and the gate. After merge, the agent deploys opt-in, outside the default set.
6. Turn on `shadow`. Add it to the AppConfig default set once it passes the `release` gate.

## 6. Code knowledge

| Knowledge | Built by | When | Stored | Used by |
| --- | --- | --- | --- | --- |
| **Code graph:** symbols, references, calls and imports, with a confidence per edge | Tree-sitter tag queries (the prototype's language-agnostic indexer) | On default-branch pushes, debounced to once per 5 minutes; on demand in Prepare if missing | `s3://<knowledge>/<repo>/<sha>/graph.sqlite`, with the latest indexed SHA in DynamoDB | blast-radius, tests, security |
| **Tests map:** which tests reach which functions | Graph edges from test files, plus CI coverage reports when the repo publishes them | With the graph | In the graph | tests, blast-radius |
| **Repo profile:** languages, frameworks, layout, test style, how routes are protected | Code scan plus one pass by a Haiku-class model, with no credentials | On install; when route, middleware or build files change | DynamoDB + S3 | security, tests, prompt headers |
| **Conventions:** numbered rules this team enforces | The learner (7.3) | On install, weekly, on `learn` | `conventions.md` in the repo once a person commits it; a snapshot until then | conventions |
| **Contracts:** OpenAPI, protobuf and JSON Schema definitions, and the code that uses each field | Contract parser (from the prototype) | With the graph | In the graph | blast-radius |

**Per review,** Prepare:
1. Loads the graph for the nearest indexed ancestor of the merge base.
2. Re-parses the files that differ (if more than 200 do, it builds from the head tree instead).
3. Overlays the PR's changes.

**Context packet:** built in code, about 10–20k tokens per agent:
- the diff
- the old and new versions of each changed symbol
- the agent's knowledge slice

v1 uses no embeddings: review needs exact facts, which the graph answers.

**Language scope:** the graph works for every language with tree-sitter tags. Language-specific rules (route finders, auth patterns, Semgrep rules, parameter adapters) ship in v1 for the two languages Bandwidth names on day 1, defaulting to Python and TypeScript.

**Upgrade path:**
- SCIP indexes
- cross-repo contract links
- Fargate indexing for very large repos

## 7. The agents

Every agent follows one recipe: **candidates → judge → verify → filter.**

| Agent | Applies when | v1 default |
| --- | --- | --- |
| security | Any source file changed | Expected to pass the gate |
| tests | Non-test source changed | Opt-in until it passes the gate and the pilot's 👍 rate |
| conventions | Conventions exist for the repo | Opt-in until conventions exist and it passes the gate |
| blast-radius | A symbol's signature or behavior changed, or a contract file changed | Expected to pass the gate |
| infra | IaC changed, or AWS SDK or database calls appear in changed functions | Opt-in until it passes the gate |

### 7.1 Security (narrow)

- **Catches exactly four things:**
  - `hardcoded-secret`
  - `sql-interpolation`
  - `unsafe-deserialization`
  - `endpoint-missing-auth`
- **Candidates:**
  - gitleaks on added lines
  - pinned, bundled Semgrep rules (`--metrics=off`, no registry access) on every changed file, whatever the size caps
  - a route finder for new or changed handlers
- **Deterministic first:**
  - A secret in a verified format (for example an AWS key ID, a GitHub token or a private key block) goes straight to a finding.
  - The judge decides only whether a lookalike is a fixture or placeholder, and may demote it to a question.
- **Context:** the code around each candidate (with secrets masked), and the repo's auth pattern.
- **Filters:**
  - Every finding cites a source and sink, or the missing guard.
  - Secrets are never repeated: only the type and the first 4 characters, plus "rotate it, don't just delete it".
  - `endpoint-missing-auth` posts to the summary only until its own eval precision reaches 0.90.

### 7.2 Tests (test gaps)

- **Catches:** new or changed logic that no test exercises.
- **Candidates:**
  - new branches in changed functions
  - tests that reach each function (from the tests map)
  - uncovered lines, from CI coverage on the PR head when the repo publishes it
- **The model decides** which gaps matter, and writes a test in the repo's framework and style. The test must pass the payload lint.
- **Filters:**
  - **At most 1 inline comment** per review: the most important untested function, or one that another agent also flagged.
  - The rest go in the summary, with the test code inside `<details>`.
  - Without coverage data, only functions that no test reaches can go inline.
  - The gate for joining the default set includes the pilot's 👍 rate, because "this is untested" is almost always *true*, even when nobody wants the comment.

### 7.3 Conventions (learner + reviewer)

- **Learner:**
  1. Reads the last 200 merged PRs' review comments, counting only reviewers with write access.
  2. A model with no credentials labels each comment and pulls out rules.
  3. Deterministic code clusters the rules, keeping each rule seen at least 3 times from at least 2 reviewers, with links to the comments.
  4. Rules a configured linter already enforces are dropped.
  5. `learn` replies with the proposed `conventions.md` (numbered `C-01`, …) for the team to edit and commit. The bot never writes to the repo, so it needs no `contents: write` permission.
- **Reviewer:** flags only violations of listed rules, each citing its rule ("Per C-07: …").

### 7.4 Blast radius

- **Change detection:** signature, behavior, rename, move, removal, contract.
- **Graph walks:**
  - direct callers, for signature and rename changes
  - up to 3 levels, for behavior changes
  - code that reads a changed contract field
  - a text fallback for YAML, SQL and templates
- **Certain breaks skip the model:** removed but still used, wrong number of arguments, a removed contract field still read.
- **The model decides,** for each caller, whether it still works with the new code.
  - A small model screens out obviously safe callers first.
  - The judge must give a concrete failing example.
- **Grouping:** all broken callers of one change go in one comment.
- **Prototype, on demo fixtures only:** caught 10/10 with no clean-PR noise. Without the graph it caught 8/10, and diff-only caught 0/10 ([results](https://github.com/rishyendra333/bandwidth-reviewer-evals/tree/main/results/2026-11-02-blast-radius-fixtures)).

### 7.5 Infra (performance and cost)

- **Cost (v1):**
  - Terraform files are parsed (`python-hcl2`) at base and head. Nothing runs, and remote modules are never downloaded.
  - The agent reports **resource changes**: added, removed, resized, instance class, Lambda memory and timeout, autoscaling, provisioned concurrency, NAT gateways.
  - No dollar figures in v1. Dollar estimates (a self-hosted Infracost pricing API, network-isolated) are in the backlog.
  - CDK changes get the same resource-level treatment from the source diff.
- **Performance (short list):**
  - N+1 queries
  - missing pagination
  - missing timeouts or retries
  - blocking calls on request paths
- **Rule:** performance comments are questions unless the code proves the problem.

## 8. Findings pipeline (filtering and presentation)

The Aggregate step turns every agent's raw findings into one review. Each stage records what it removed or moved and why (the contract's `dropped` list), so evals can see whether a filter throws away real issues.

| # | Stage | What it does | Recorded reason |
| --- | --- | --- | --- |
| 1 | Validate | Schema check; normalize paths | `schema_invalid` |
| 2 | **Verify evidence** | Every cited `path:line` exists at the head commit, any quoted code appears there, and the finding's own line exists. Stops made-up files (diff-only cited nonexistent files in over a third of its first-run comments) | `unverified_evidence` |
| 3 | Ignore rules | `ignore_paths`, merge-base-era ignore markers, generated or vendored files | `ignored` |
| 4 | Threshold | Below the agent's calibrated confidence floor, or under `min_severity` | `below_threshold` |
| 5 | Suppress | Already posted on this PR, dismissed in this repo, or already reported by a configured linter | `suppressed` |
| 6 | **Group and dedupe** | Same root cause → one finding listing the affected locations. Same line and same issue → one finding naming both agents. Same line and different issues → one comment with sections | `merged` |
| 7 | Anchor | Inline only if the line is on the RIGHT side of a hunk in GitHub's patch (and `start_line` is in the same hunk). Otherwise it snaps to the changed line that causes it, or goes to the summary. Files without a patch are summary-only | `moved_to_summary` |
| 8 | Rank | Severity (critical 4, high 3, medium 2, low 1) × confidence × agent priority (security first) | |
| 9 | Cap | 10 inline in total; 4 per agent, 3 per file, 1 for tests. **Critical and high findings are exempt** from the per-agent and per-file caps, and any high finding that can't go inline is listed in the visible part of the summary | `capped` |
| 10 | **Payload lint** | Suggestions and test code: size cap; covers only the commented lines; no URLs; no new imports except the repo's own modules and its test framework (for generated tests); no `exec`/`eval`/`subprocess`/shell calls; no encoded blobs; gitleaks and Semgrep pass. Failures become plain text "Possible fix", or are dropped | `payload_rejected` |
| 11 | Render and sanitize | Rendered from structured fields with the templates in 3.4. Escape `@`, `#123` and `org/repo#123` references, and bare URLs outside code. Links only to permalinks in this repo. Redact token-like strings. Add the hidden run marker | |

**Fingerprint:** agent + rule + canonical symbol or file + a hash of the normalized evidence snippet. There are no line numbers and no versions, so a fingerprint survives rebases, and changed code gets a new one.

**Feedback:**

| Signal | When it's collected | Counts as |
| --- | --- | --- |
| 👍/👎 reactions | When the PR closes (GitHub sends no reaction webhooks) | Usefulness |
| Thread resolved by a person | By webhook | Acknowledged; not evidence of correctness |
| Commented code changed in a later commit | By webhook | Useful |
| `dismiss wrong` | By webhook | False positive |
| `dismiss wontfix` | By webhook | Correct but accepted; never counted as a false positive |

All feedback is stored per fingerprint and agent version.

## 9. Configuration

The config file is `.github/bandwidth-reviewer.yml`, read from the **default branch**. When a PR changes it, the review summary validates the PR's version too. Every key is optional.

```yaml
version: 1
agents:
  default: [security, blast-radius]          # optional: narrows the AppConfig default set for this repo
  security:     {enabled: true, min_confidence: 0.90, public_routes: ["GET /health"]}
  tests:        {coverage_artifact: "coverage.xml"}
  conventions:  {file: .github/bandwidth-reviewer/conventions.md, learn_from_last_n_prs: 200}
  blast-radius: {hub_threshold: 20, contract_globs: ["openapi/**", "proto/**"]}
  infra:        {}
ignore_paths: ["**/generated/**", "**/*.snap", "docs/**"]
max_comments: 10
min_severity: medium
log_prompts: false       # true keeps prompt/response logs for this repo (30 days, break-glass access)
```

- Thresholds in config can only **raise** an agent's calibrated floor.
- Unknown keys or bad values fall back to defaults, and the summary names the line and the closest valid key.
- A JSON Schema is published for editor validation.

## 10. Security and privacy

| Threat | Control |
| --- | --- |
| **Running PR code** | Never checked out, installed, built or run. Files come from git objects, without symlinks or submodules. Scanners run offline with pinned rules (Semgrep `--metrics=off`, no registry). HCL is parsed, never run, and modules are never downloaded |
| **Agents reaching out** | Everything that parses untrusted code (Prepare, agents, Aggregate) runs in private subnets with no NAT. The only routes out are the S3, DynamoDB, Bedrock and X-Ray endpoints. Their policies are pinned to our account, buckets and tables, and DNS Firewall allows only those names. Agents have no GitHub credentials, and reach S3 only through this run's presigned URLs (valid 15 minutes). Tests prove outbound HTTP and DNS lookups fail |
| **Prompt injection: leaking code** | Tool paths are confined to the bundle root; `/tmp` is wiped at start and end; each run's bundle has its own URLs. Agents can't see other runs or repos |
| **Prompt injection: silencing findings** | Deterministic findings can't be dropped by the model, only demoted, and the summary counts demotions. Ignore markers count only if they existed at the merge base. Scanners run on every changed file, regardless of size caps. PR authors can't dismiss security findings on their own PRs. Injection cases are in every agent's eval set |
| **Prompt injection: payloads and spam** | Payload lint on suggestions and test code. Comments are rendered from structured fields, with mentions, cross-references and bare URLs escaped |
| **Budget exhaustion** | Write access is required to trigger; quotas per user, repo and org; per-agent concurrency limits; tool regexes run on RE2 |
| **GitHub credentials** | The App key lives in KMS as sign-only, and only the Token broker can sign. Each caller has its own broker alias, and its scope comes from that alias, never from the request (section 4.2). Tokens are scoped to one repo and the fewest permissions. They're never stored in Step Functions state, logs or X-Ray, never seen by a model, and never held by code that parses PR content |
| **Unwanted installs** | Private App, plus an installation-ID allowlist |
| **Webhook endpoint** | Constant-time signature check first; only relevant actions; API Gateway throttling; reserved Ingress concurrency; two secrets during rotation |
| **CI/CD and Terraform** | Actions pinned to SHAs. OIDC roles with pinned `sub`: plan is read-only, and fork PRs are never planned; prod apply needs environment approval. CODEOWNERS on manifests, prompts, infra and the pipeline. Manifest schema validation. State encrypted, with no secrets in it |
| **Supply chain** | uv lockfile with hashes; base image pinned by digest; grammars and scanners pinned by version and checksum; ECR immutable and scanned |
| **Data stores and retention** | See the table below. Uninstalling runs the purge function, which deletes all versions of the repo's S3 objects and its DynamoDB items within 7 days. Logs and Step Functions history can't be purged per repo; they hold no code and age out on their own. `SECURITY.md` lists every store |
| **Operator access** | Prompt logs are off by default. When on, they are readable only through a break-glass role, with CloudTrail data events on that bucket |
| **Audit** | Every review, command, dismissal, config change and release is logged with actor and run ID |

**Data stores:**

| Store | Contains code? | Retention |
| --- | --- | --- |
| Tree cache, run bundles | Yes | 7 days; noncurrent versions 1 day |
| Agent outputs, rendered reviews | Snippets in findings | 30 days |
| Prompt logs (only with `log_prompts: true`) | Yes | 30 days, break-glass |
| Knowledge (graphs, profiles) | Symbols and snippets | 30 days after creation (the latest graph is rebuilt on the next push or on demand) |
| CloudWatch Logs | No (no code or findings logged) | 30 days |
| Step Functions history | No (IDs and S3 keys only) | 90 days (fixed by AWS) |
| DynamoDB | No (IDs, fingerprints, counts) | Item TTLs; PITR 35 days |
| Bedrock invocation logging | Would contain prompts | Account- and Region-level setting: must be off or metadata-only. Checked on day 1 and by `bwr doctor` |

## 11. Evaluation pipeline

The eval pipeline lives in [bandwidth-reviewer-evals](https://github.com/rishyendra333/bandwidth-reviewer-evals) and gates every agent. Its full design is `docs/eval-plan.md`, and the step-by-step guide is `RUNBOOK.md`. **At handoff it moves to a Bandwidth-owned private repo**, before any production feedback or Bandwidth code is added.

### 11.1 One contract

```bash
bwr review --repo-path PATH --base SHA --head SHA --merge-base SHA [--agents a,b] --out result.json
```

This runs the production code path up to rendering, and writes `bwr.review/v1` (the eval repo's `docs/reviewer-contract.md`). Production agents write the same format to S3.

### 11.2 Eval sets

| Set | Contents | Used for |
| --- | --- | --- |
| `smoke` | Planted fixtures, plus injection and hostile-file cases. Today: the 13 blast-radius fixtures with the rules-only reviewer. Each agent adds its own fixtures and recorded model replies as it's built | Every commit (no model calls) |
| `dry-run` | 5 cases per source | Checking cost and plumbing before a big run |
| `regression` | Test split, stratified by source | Every PR that changes a prompt, model, tool, filter or knowledge builder |
| `full` | Dev + test | Nightly or weekly |
| `release` | **Holdout from our own sources:** mined, traced and tool-labeled cases from the ~20% of repos chosen by repo hash, never tuned on, mostly PRs merged after July 2026. Public benchmarks are never in it | Release decisions, after a code freeze |

**Sources:**
- public benchmarks: SWE-PRBench and Qodo PR-Review-Bench
- our fixtures
- mined review comments that a later commit fixed
- fixes traced back to the PR that caused them
- tool-labeled cases: mutations, coverage, and Terraform resource diffs
- production feedback

### 11.3 Scoring and the judge

1. **Rule matching:** same file and nearby lines, or the same symbol and caller.
2. **An LLM judge:** a different, stronger model than the agent under test, with a written rubric.
   - Two people re-label a random sample of its verdicts. The judge is trusted at ≥ 90% agreement over at least 20 rows.
   - Agreement is measured **before** its verdicts are used for calibration.
3. **Metrics,** per agent and for the whole review:
   - recall
   - grounded and augmented precision
   - clean-PR noise
   - comments per PR (mean and p90)
   - duplicates
   - true positives the filters dropped
   - severity mix
   - cost
   - p50/p95 latency
   - errors

   Rates come with Wilson intervals. Releases are compared with a paired McNemar test.

### 11.4 Feedback becomes eval cases

- `dismiss wrong` → candidate *must-not-flag*
- 👍, or comments the author then fixed → candidate *must-flag*
- issues humans caught on the same PR that the bot missed → candidate *missed*
- `dismiss wontfix` → no case (the finding was correct)

A person confirms each candidate before it joins a set.

### 11.5 Calibration

`evals calibrate` sets each agent's `min_confidence` from dev-set results (using the trusted judge): the lowest threshold where precision meets the target with a Wilson lower bound ≥ 0.70. It writes the value into the manifest for review.

**When a Bedrock model changes,** calibration and the gate are re-run before the new model goes `live`. `RUNBOOK.md` has a model-upgrade procedure, rehearsed once before handoff.

### 11.6 Release stages

1. **PR:** tests, recorded-model tests, and `evals gate` on `regression`: no significant drop in catches, no significant rise in wrong findings, targets met.
2. **Shadow:** the new version runs on the `shadow` alias for real reviews. Its findings are logged, not posted.
3. **Live:** `live` moves to the new version once the `release` set passes on frozen code. Any agent can be rolled back by moving the alias, which takes seconds.
4. **Default:** the agent is added to the AppConfig default set after the release gate, and, for tests, after the pilot's 👍 rate.

## 12. Operations

**Dashboards:**
- reviews requested, posted and failed
- latency per step and per agent
- findings and drop reasons per agent
- cost per agent and per day
- Bedrock throttling
- index freshness
- feedback per agent

**Alarms:**
- DLQ depth above 0
- failure rate above 5% over 1 hour
- an agent's error rate above 10% over 1 hour
- Bedrock throttling
- daily cost over budget
- an agent's `dismiss wrong` rate above 30% in a week
- index lag over 1 hour
- the Finalizer fired more than 3 times in an hour

**Kill switches** (AppConfig): global, per org and per agent, effective in seconds. **Rollback:** move an agent's `live` alias, or redeploy the previous image digest.

**Runbooks:**
- DLQ redrive
- Step Functions redrive
- an agent failing or noisy
- Bedrock outage or throttling
- cost spike
- stuck index
- `422` on post
- webhook secret rotation
- App key rotation (KMS)
- model upgrade
- restoring a deleted install

**Environments:**

| Environment | GitHub App | Repos | Deploy |
| --- | --- | --- | --- |
| `dev` | `bandwidth-reviewer-dev` (trigger `@bandwidth-reviewer-dev`) | Sandbox repos | `infra/envs/dev` |
| `prod` | `bandwidth-reviewer` (trigger `@bandwidth-reviewer`) | Bandwidth repos | `infra/envs/prod`, behind an approval |

Shadow aliases in prod replace a staging environment.

**Ownership:**
- Handoff requires a **named Bandwidth owning team**.
- Each agent has an owner listed in its manifest.
- Each student owner records a 20-minute code walkthrough of their area.

## 13. Handoff to Bandwidth

| Deliverable | Contents |
| --- | --- |
| `bandwidth-reviewer` repo (transferred to Bandwidth's org) | Platform, SDK, knowledge layer, five agents, Terraform modules and environments, CI and deploy workflows, CODEOWNERS |
| `bandwidth-reviewer-evals` repo (transferred, private) | Harness, cases, results, runbook |
| GitHub App manifest | Creates the private App in Bandwidth's org with the right permissions, events and allowlist |
| Docs | `README.md` (overview, usage), `INSTALL.md`, `ADDING-AN-AGENT.md`, `RUNBOOK.md`, `SECURITY.md` (threat model and data handling) |
| Eval report | Per-agent results against baselines on public benchmarks and the holdout; cost, latency and known limits |
| Deployed stack | In Bandwidth's account if access is granted; otherwise, `terraform apply` verified on a clean account |
| Walkthroughs | One recorded video per area |
| Pilot proposal | Named owner, 3 pilot repos, a 30-day pilot with dates, and the success metrics in section 2 |

## 14. Open questions for Bandwidth (asked on day 1)

1. Which AWS account and region? Can the team create IAM roles there, or is there a sandbox account?
2. Which Bedrock models are approved, in which geography, and with what tokens-per-minute quota? Is model invocation logging on in that account, and has the Anthropic first-use form been submitted?
3. github.com or GitHub Enterprise Server? GitHub Enterprise Server changes how webhooks reach AWS.
4. What are the top two languages? Do pilot repos publish CI coverage? Is the IaC mostly Terraform or CDK?
5. Does sending source code to Bedrock in their account need a compliance review? (`SECURITY.md` goes to them on day 2.)
6. Who owns the service after handoff, which team pilots it, and which Slack channel handles support?

## Appendix A. Shared schemas

```python
class Finding(BaseModel):                       # also the `findings[]` entries in bwr.review/v1
    id: str                                     # "SEC-1", assigned by the aggregator
    agent: str
    rule: str                                   # "security/sql-interpolation", "conventions/C-07"
    severity: Literal["critical", "high", "medium", "low"]
    confidence: float = Field(ge=0, le=1)
    file: str
    line: int
    end_line: int | None = None
    symbol: str | None = None
    affected: list[str] = []                    # "app/bulk_send.py:31 send_bulk"
    title: str                                  # ≤ 100 characters
    body: str                                   # markdown; the renderer adds structure
    example: str | None = None                  # required for behavior findings
    suggestion: str | None = None               # exact replacement for line..end_line; payload-linted
    evidence: list[str]                         # ["app/db.py:40"]; verified in stage 2
    deterministic: bool = False                 # from a rule; the model may demote, never drop
    placement: Literal["inline", "summary"] = "inline"
    fingerprint: str = ""

class ReviewContext(BaseModel):
    run_id: str; repo: str; pr: int | None; base: str; head: str; merge_base: str
    title: str; body: str
    diff: list[FileDiff]                        # hunks + commentable RIGHT-side lines from GitHub's patches
    changed_symbols: list[ChangedSymbol]
    config: RepoConfig
    agents: list[str]
    knowledge: dict[str, Any]                   # per-agent slices
    limits: Limits                              # what was skipped and why
```

## Appendix B. Optional: RL fine-tuning

Consider this only if an agent misses its cost or precision target after prompt and threshold tuning.

- **What to train:** a small open-weight model, using RL with verifiable rewards from the eval sets' automatic answer keys:
  - mutations whose tests fail
  - CI coverage
  - history replay
- **Where it's used:** only in the screen or verify step.
- **Ship rule:** it replaces the prompted model only if it wins on the human-labeled real-PR sets, which it never trained on.

## Appendix C. Decisions and alternatives

### C.1 How the bot shows it's working

| Option | Good | Bad | Decision |
| --- | --- | --- | --- |
| Reactions, 👀 then 🚀 (the prototypes) | Instant; no notifications | Say nothing about progress, agents or failures; easy to miss | Replaced |
| Check run only | GitHub's native status place; updates in place | Updates send no notifications; it's one row among many CI checks, and it's tied to the head commit, so a push hides it | Kept as a secondary surface |
| **Status comment under the trigger, edited in place, plus the check run** | Visible where the person typed, on mobile and in email; shows failures; one comment per request, with older ones hidden | One notification per request | **Chosen** |

### C.2 Why one Lambda per agent

| Option | Good | Bad | Decision |
| --- | --- | --- | --- |
| **Lambda per agent behind Step Functions** | Mature; cheap at this volume; per-agent IAM, VPC, limits, versions and aliases; one Terraform module per agent | 15-minute cap (agents get 5); cold starts (mitigated with a slim Dispatcher image plus provisioned concurrency); `/tmp` can survive between warm invocations (wiped at start and end) | **Chosen** |
| [Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-instances-how-it-works.html) | Built for agents; a microVM per session; sessions up to 8 hours; built-in observability | Newer; billed for the whole session; needs Bandwidth approval; adds little for 1–5 minute stateless reviews | Upgrade path for long or stateful agents |
| ECS Fargate workers | No time cap | Always-on or slow start; more ops | Backlog: very large repos |
| Bedrock Agents (managed) | No loop code | Less control over budgets and forced finishes; hard to record and replay for evals | Rejected |

**Agent framework:** our own thin SDK on the Converse API (5.3). It grows out of the blast-radius prototype's loop, which already has budgets, forced finish and record/replay, with 69 tests. [Strands Agents](https://github.com/strands-agents/sdk-python) (Apache-2.0) is acceptable for an agent whose owner prefers it; the agent interface hides the choice.
