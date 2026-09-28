# Week 1 execution checklist

## Recorded configuration
- Hosting account: **516647891652**, region **us-west-2**, deployment-owner profile **default**.
- Teammate IAM user ARNs: pending; inspection is disabled until exact identities are supplied.
- Bedrock model and permitted inference regions: sponsor confirmation pending; fake client is the default.
- Shared GitHub App owner: **AlexShen12** (temporary; handoff planned). Sandbox: **rishyendra333/bandwidth-reviewer-demo**.
- Shared/per-developer GitHub App registration, secrets, and help channel: record in the team setup handoff.

## Owner and developer tasks

| Day | Developers | Deployment owner |
|---|---|---|
| 1 | Register personal Apps; setup tools/profiles; agree on Job, ReviewContext, Finding | Verify account and permissions; collect ARNs; obtain model/region confirmation |
| 2 | Run local Moto/ingress/stub/smee; parser tests | Bootstrap versioned locked state; register shared App and prepare secrets |
| 3 | Ingress signature/event/delivery tests | Plan/apply API, Lambda, queues, tables, logs, secret containers |
| 4 | Personal sandbox testing | Populate secrets, connect webhook, verify inspection role and deployed smoke test |
| 5 | Fresh-clone onboarding, CI, local E2E | Actual GitHub PR demo and deployment handoff |

## Acceptance evidence
- [ ] A real PR command enqueues one job; measure ingress-to-enqueue duration (target <=1 second, cold starts reported separately).
- [ ] Redelivering a successful delivery adds no job.
- [ ] Bot, non-PR, edited, unrelated, and another app's trigger events are ignored.
- [ ] Invalid signature returns 401.
- [ ] Installation events persist idempotently.
- [ ] Pending leases, expired takeover, enqueue failure, and post-send crash recovery tests pass.
- [ ] Logs correlate delivery/message IDs and contain no credential payloads.
- [ ] Teammate can assume project inspection role; secrets/state/mutations remain denied.
- [ ] Wrong-account guard and state locking verified; a following plan is unchanged.
- [ ] Teammate can complete documented setup, tests, and local E2E.
- [ ] Record Bedrock approval or blocker; perform Converse smoke test once approved.

## Handoff outputs
Share resource identifiers and the console switch-role URL from `.build/outputs.json`, reviewed commit and plan/package hashes from `.build/deployment.json`, safe acceptance logs, and GitHub demo delivery ID. Saved plans, state, and secrets remain private to the owner.
The shared worker container (3 GB memory, 4 GB temporary storage, 15 minutes; batch size 1, maximum concurrency 5) is the next milestone.
