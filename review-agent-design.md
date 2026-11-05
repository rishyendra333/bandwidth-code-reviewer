# Review Agent — Simple Design

Oct 22, 2026 · The short, plain-language version. **Where it differs from [production-spec.md](production-spec.md) (v3, Nov 4), the production spec wins**: for example, the status comment instead of reactions, Lambda per agent behind Step Functions instead of one Fargate worker, and Terraform. We build and own every part: the app, the infra, the code knowledge and the agents.

**What it does:** someone comments `@bandwidth-reviewer review` on a PR. A few minutes later, one review appears with inline comments on the changed lines. It never blocks merges, never pushes code and never runs on its own.

## 1. The flow

```text
PR comment ──► GitHub App webhook ──► Lambda (verify, queue) ──► SQS ──► Review worker (Fargate)
                                                                           │
   1. Prepare      diff + changed functions + repo knowledge ──► context packet per agent
   2. Orchestrate  plain code picks which agents apply, runs them in parallel
   3. Agents       each one: candidates from code → Claude judges with tools → findings
   4. Aggregate    keep only diff-line findings, dedupe, rank, cap at 10
   5. Post         one GitHub review with inline comments
                                                                           │
                                           Bedrock (Claude) · S3 (code graph, logs) · DynamoDB (state, knowledge)
```

**Infra, all in our AWS account:**

| Piece | Why |
| --- | --- |
| GitHub App | One install per org, no per-repo setup, its own bot identity and short-lived tokens |
| API Gateway + Lambda | Answers GitHub within 1 s and queues the job |
| SQS | Absorbs bursts and retries failed jobs |
| Fargate worker service (always on, autoscaled) | Reviews can take minutes and need git, parsers and scanners. Lambda's limits are too tight |
| Bedrock | Claude runs in our account, so code never leaves it |
| S3 + DynamoDB | Code graphs and logs in S3. Run state, per-repo knowledge and feedback in DynamoDB |

That is the whole system. Everything else is the agents and what we feed them.

## 2. Code knowledge (the part that makes agents good)

An agent is only as good as the context it gets. Pasting the whole repo into the prompt is too big and too noisy. Pasting only the diff misses everything around it. So we **build repo knowledge ahead of time**, then give each agent the **exact slice it needs**, plus tools to fetch more.

### 2.1 What we build per repo

This is refreshed on every push to the default branch and stored in S3 and DynamoDB.

| Knowledge | How we build it | Used by |
| --- | --- | --- |
| **Code graph:** every function and class, who calls what, imports | Tree-sitter parses every file (any language) into a SQLite graph. Later, SCIP indexers for exact, compiler-level links | Blast radius, tests, security |
| **Tests map:** which tests reach which function | From graph edges coming out of test files | Tests, blast radius |
| **Repo profile:** languages, frameworks, folder layout, how routes are protected, test style | A one-time agent pass over the repo, re-run when key files change | Security, tests, all agents' prompts |
| **Conventions:** rules this team actually enforces | Learned from the last 200 merged PRs' human review comments (6.3) | Conventions |
| **Contracts:** API definitions (OpenAPI, protobuf) and who uses each field | Parsed from contract files and linked to code that reads them | Blast radius |

### 2.2 How it reaches each agent

1. **Context packet, built in code before the model is called.** It holds the diff, the full text of each changed function (old and new), and the agent-specific slice:
   - blast radius: the callers of each changed function
   - tests: the tests that reach each change
   - security: the repo's auth pattern

   This keeps it small, around 10–20k tokens, and every token is relevant.
2. **Read-only tools** let the agent pull more when the packet isn't enough:
   - `read_file`, `grep`, `get_diff`
   - `get_callers`, `find_tests`, `get_symbol` (from the graph)
   - `get_conventions`, `get_repo_profile` (from the knowledge store)

   There is no shell, no network access and no write access.
3. **Prompt caching** on the system prompt and the packet, so the agent's later turns are cheap.

Why not RAG or embeddings? Review needs exact facts ("who calls this function"), not "code that looks similar". The graph gives exact answers. Embeddings can be added later for one job: finding examples, such as a neighboring test to copy the style from.

## 3. The orchestrator

It is plain code, not an LLM. Whether each agent should run is a simple yes/no question about the diff:

| Agent | Runs when |
| --- | --- |
| Security | Any source file changed |
| Tests | Non-test code changed |
| Conventions | The repo has learned conventions |
| Blast radius | A function's signature, behavior or an API contract changed |
| Infra (perf + cost) | IaC files changed, or database or AWS calls in changed code |

Agents run in parallel, each with its own time limit, so one slow or failing agent never blocks the others. The aggregator then:
- drops anything not on a diff line, or moves it to the summary
- merges duplicates
- ranks by severity
- caps the review at 10 comments, with at most 4 per agent

**Why not one big agent?** One prompt trying to do everything does each job worse, runs slower, and can't be measured or tuned one area at a time.

## 4. How every agent is built (same recipe)

```text
1. Candidates   deterministic code finds possible issues   (cheap, repeatable)
2. Judge        Claude reads the context packet + uses tools to confirm or reject each one
3. Verify       a second, fresh Claude call checks each surviving finding against the cited code
4. Filter       code enforces rules: evidence required, confidence floor, on a diff line
```

What makes an agent good:
- **The model judges candidates instead of inventing issues.** This is the biggest precision lever.
- **Every finding must cite evidence:** the file and line, plus a concrete example of the failure. "This might cause issues" is never posted.
- **Narrow scope per agent.** A short list of things done well beats a long list done badly.
- **Its own eval set** (section 6). We can't make an agent better without measuring it.

## 5. Each agent

### 5.1 Security

- **Looks for exactly four things:** hardcoded secrets, SQL built from strings, unsafe deserialization, and new endpoints missing the repo's auth check.
- **Candidates:** gitleaks (secrets) and Semgrep rules (SQL, deserialization), run on changed lines. A route finder lists new or changed endpoints.
- **Context:** the code around each candidate, and the repo's auth pattern from the repo profile.
- **The agent decides:**
  - Is this secret real or a test fixture?
  - Does user input actually reach this query?
  - Does this route have the same guard as its neighbors?
- **Best-in-class detail:** a secret is never repeated in the comment (only its type and first 4 characters), and the comment says to rotate it, not just delete it.

### 5.2 Test gaps

- **Looks for:** new or changed logic that no test exercises.
- **Candidates:** tree-sitter lists the new branches in each changed function (`if`/`else`, early returns, `catch`). The tests map gives the tests that reach that function. If CI uploads a coverage report, it says exactly which lines are uncovered.
- **Context:** the changed function, its tests, and one neighboring test file as a style example.
- **The agent decides** which gaps matter, and writes **a ready-to-paste test** in the repo's own framework and style, not "please add tests".
- **Best-in-class detail:** one comment per function, listing the missing cases. It skips getters, logging and generated code.

### 5.3 Conventions

- **Learner** (runs once on install, then weekly):
  1. Reads the last 200 merged PRs' human review comments.
  2. A small model labels each comment: convention, bug, question or other.
  3. Similar rules are grouped. Rules seen at least 3 times, from at least 2 reviewers, are kept, with real example comments.
  4. They're saved as numbered rules (`C-01`, `C-02`, …) in a `conventions.md` that the team can edit.
- **Reviewer:** gets the rule list and the diff, flags only violations of those rules, and cites the rule ("Per C-07: …") with a link to past examples.
- **Best-in-class detail:** teams accept rules they already enforce. Rules a linter already catches are dropped.

### 5.4 Blast radius

- **Looks for:** code outside the diff that the change breaks.
- **Candidates:** compare old and new versions of each changed function (signature or behavior change), then walk the graph:
  - signature and rename changes: direct callers
  - behavior changes: up to 3 levels of callers
  - contract changes: code reading the changed field
  - YAML and config: references by name

  Certain breaks are posted with no model call: a removed function still called, or a wrong number of arguments.
- **Context:** each changed function (old vs new), and each caller the PR didn't update, with the lines around the call.
- **The agent decides**, for each caller, "given the new code, does this still work?" It gives a concrete failing example ("161 chars now bills 1 segment instead of 2").
- **Best-in-class detail:** a cheap model screens obviously safe callers first, so the strong model spends its turns on the risky ones.

### 5.5 Infra (performance + cost)

- **Looks for:**
  - cost jumps in Terraform
  - a short performance list: N+1 queries, missing pagination, missing timeouts or retries, blocking calls on request paths, Lambda and database sizing changes
- **Candidates:** Infracost on base vs head Terraform (it reads the files; nothing is run, and pricing data comes from our self-hosted pricing service). Tree-sitter finds database and AWS calls inside loops.
- **The agent decides** whether each pattern is a real problem in context.
- **Best-in-class detail:** a dollar amount is shown only when Infracost computed it. Performance comments are phrased as questions ("Is this list bounded?") unless the code proves the problem.

## 6. Making each agent better over time

| Agent | Eval set with automatic answers | How we use it |
| --- | --- | --- |
| Security | Planted secrets and vulnerabilities in real code | Precision target ≥ 0.9 |
| Tests | PRs where CI coverage shows exactly which new branches are untested | Did it flag the real gaps? |
| Conventions | Learn from old PRs, then review newer ones: did it flag what humans later commented on? | Recall, plus human-rated precision |
| Blast radius | Break a function on purpose, run the repo's tests; the failing tests mark the broken callers | Caught breaks vs false alarms |
| Infra | Real Terraform PRs with known cost changes, plus planted performance patterns | Precision |

- Every prompt or model change re-runs that agent's eval set in CI and must not get worse.
- A set of **clean PRs** for every agent checks that it stays quiet when nothing is wrong.
- Live feedback (👍/👎 and `@bandwidth-reviewer dismiss`) is stored per finding, and dismissed findings become new eval cases.
- Later, these automatic answer keys can also serve as RL rewards to fine-tune smaller models for the yes/no judging steps.

## 7. Build order

1. **Platform with one generic agent:** the app, queue, worker, posting and logging, end to end on the demo repo.
2. **Code knowledge layer:** the tree-sitter graph, tests map and repo profile, refreshed on push.
3. **Agents, one at a time**, each with its eval set from day one: security → blast radius → tests → conventions → infra.
4. **Tune** each agent against its evals, then pilot on real Bandwidth repos.
5. **Upgrades when evals show the need:** SCIP for exact code links, cross-repo contracts, RL for the judge steps.
