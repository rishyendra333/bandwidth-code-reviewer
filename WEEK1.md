# Week 1 execution checklist

## Recorded configuration
- Hosting account: **516647891652**, region **us-west-2**, deployment-owner profile **default**.
- Teammate IAM user ARNs: pending; inspection is disabled until exact identities are supplied.
- Bedrock model and permitted inference regions: sponsor confirmation pending; fake client is the default.
- Shared GitHub App owner: **AlexShen12** (temporary; handoff planned). Sandbox: **rishyendra333/bandwidth-reviewer-demo**.
- Shared App: **bandwidth-reviewer-dev**, App ID **5109565**, [settings](https://github.com/settings/apps/bandwidth-reviewer-dev). Installed on `rishyendra333` in selected-repository mode; installation ID **165828858**.
- Per-developer App registrations and the help channel: record in the team setup handoff.

## Owner and developer tasks

| Day | Developers | Deployment owner |
|---|---|---|
| 1 | Register personal Apps; setup tools/profiles; agree on Job, ReviewContext, Finding | Verify account and permissions; collect ARNs; obtain model/region confirmation |
| 2 | Run local Moto/ingress/stub/smee; parser tests | Bootstrap versioned locked state; register shared App and prepare secrets |
| 3 | Ingress signature/event/delivery tests | Plan/apply API, Lambda, queues, tables, logs, secret containers |
| 4 | Personal sandbox testing | Populate secrets, connect webhook, verify inspection role and deployed smoke test |
| 5 | Fresh-clone onboarding, CI, local E2E | Actual GitHub PR demo and deployment handoff |

## Acceptance evidence
- [ ] A real PR command enqueues one job; the repository installation is verified, but the real PR comment has not yet been posted. Measure ingress-to-enqueue duration (target <=1 second, cold starts reported separately).
- [x] Redelivering a successful synthetic delivery adds no job; real GitHub PR redelivery remains pending installation.
- [x] Bot, non-PR, edited, unrelated, and another app's trigger events are ignored (mocked tests; bot/unrelated also verified in AWS).
- [x] Invalid signature returns 401 (mocked and deployed).
- [x] Installation events persist idempotently in tests and the real installation event is recorded in DynamoDB (`INSTALLATION#165828858`).
- [x] Pending leases, expired takeover, enqueue failure, and post-send crash recovery tests pass.
- [x] Logs correlate delivery/message IDs and contain no credential payloads.
- [ ] Teammate can assume project inspection role; secrets/state/mutations remain denied.
- [x] Wrong-account guard and state locking verified against AWS; following bootstrap and application plans are unchanged.
- [ ] Teammate can complete documented setup, tests, and local E2E.
- [x] Bedrock approval blocker recorded; fake execution and approval gate tested.
- [ ] Perform Converse smoke test after approved models and inference destinations are confirmed.

## Verified deployment — September 28, 2026

| Item | Evidence |
|---|---|
| Source | Branch `codex/week1-terraform`; deployed code commit `b6fa3e8fe16df1f6a8b409ee918c4b87b3d15d34` |
| Developer setup | `make setup` installed locked Python/npm dependencies and hooks in the repository |
| Python checks | Ruff, formatting, mypy, and **38 passing pytest tests** |
| Terraform checks | Both configurations validate; **5 passing mock infrastructure tests** |
| Local pipeline | `make e2e` passed through HTTP → Moto → worker stub |
| Live resources | **5 bootstrap + 16 application resources** created in `516647891652 / us-west-2` |
| State | Versioned AES256-encrypted S3 objects under separate `bootstrap/` and `dev/` keys; a concurrent plan rejected the temporary native S3 lock |
| Account guard | A real Terraform plan configured for another account was rejected; no resource mutation occurred |
| Rebuild | Two Linux x86_64 builds produced the same ZIP hash; following application and bootstrap plans show no changes |
| GitHub connectivity | Signed `ping` delivery `df5321b6-bb4b-11f1-8ef5-9fc5bef7706d` returned **200** |
| Deployed smoke | Delivery `c92013e6-5f24-4d5f-a77a-0da9cc4d5dbe`, SQS message `333ec904-1f4d-45ff-be2f-45583aad66c3`; DynamoDB `queued`, duplicate `200`, exactly one matching job |
| Timing | Application handling **284.71 ms**; duplicate **15.35 ms**. First Lambda invocation: **864.74 ms** execution plus **1125.51 ms** cold initialization; a one-second cold-start HTTP response is not demonstrated |
| Secrets | Random webhook signing secret and matching GitHub RSA private key stored directly in separate Secrets Manager resources |

The smoke test deletes only its own synthetic job after verification. Its delivery record and correlated CloudWatch logs remain available until their configured retention expires. The real PR comment demo, teammate inspection test, and teammate onboarding test remain outstanding.

### Shared resource identifiers

- Webhook: `https://ec98u7cq85.execute-api.us-west-2.amazonaws.com/webhook`
- Review queue: `https://sqs.us-west-2.amazonaws.com/516647891652/bandwidth-reviewer-dev-jobs`
- Dead-letter queue: `https://sqs.us-west-2.amazonaws.com/516647891652/bandwidth-reviewer-dev-dlq`
- Tables: `bandwidth-reviewer-dev-deliveries`, `bandwidth-reviewer-dev-runs`
- Log group: `/aws/lambda/bandwidth-reviewer-dev-ingress`
- State bucket: `bandwidth-reviewer-tfstate-516647891652-us-west-2`
- Secret names: `bandwidth-reviewer-dev/webhook-secret`, `bandwidth-reviewer-dev/github-private-key`

### Finish the real GitHub demo

1. The repository owner has installed [the App](https://github.com/apps/bandwidth-reviewer-dev) with selected-repository mode; installation ID **165828858** is recorded in DynamoDB.
2. On [sandbox PR #1](https://github.com/rishyendra333/bandwidth-reviewer-demo/pull/1), post `@bandwidth-reviewer-dev review`.
3. In the App's Recent Deliveries, verify `issue_comment` returned 200. Use its delivery UUID to find the DynamoDB `queued` record and CloudWatch message ID, then inspect the corresponding SQS job.
4. Redeliver that delivery and confirm a `duplicate` response with no additional enqueue. Queue reads affect visibility and receive counts; use only the sandbox demo job for this inspection.

## Handoff outputs
Share resource identifiers and the console switch-role URL from `.build/outputs.json`, reviewed commit and plan/package hashes from `.build/deployment.json`, safe acceptance logs, and GitHub demo delivery ID. Saved plans, state, and secrets remain private to the owner.
The shared worker container (3 GB memory, 4 GB temporary storage, 15 minutes; batch size 1, maximum concurrency 5) is the next milestone.
