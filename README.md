# Bandwidth code reviewer — Week 1

Python webhook intake and Terraform infrastructure for **PR comment → API Gateway → Lambda → SQS**.
Week 1 queues commands; the local worker logs them using a fake client. GitHub review posting belongs to Milestone 2.

## Start locally

```sh
make setup
cp .env.example .env
# Set your personal TRIGGER, WEBHOOK_SECRET, and optional SMEE_URL in .env.
make dev
```

For local-only onboarding before AWS CLI/Terraform installation, use `make setup-local`.
`make test` exercises mocked services; `make e2e` starts its own isolated local stack and verifies HTTP intake, deduplication, and worker consumption.
`make lint` also validates Terraform; `make lint-python` runs Python-only checks.

- [CONTRIBUTING.md](CONTRIBUTING.md): development in fewer than ten steps.
- [INSTALL.md](INSTALL.md): developer authentication, GitHub Apps, shared AWS deployment, secrets, and access.
- [WEEK1.md](WEEK1.md): owner checklist and evidence required for the demo.
- [implementation-plan.md](implementation-plan.md): milestone roadmap, updated for Terraform.

## Boundaries

Shared hosting is account **516647891652**, Oregon **us-west-2**, using the owner's `default` AWS profile.
Each teammate has a separate Bandwidth account and a personal local GitHub App. Supply exact teammate IAM user ARNs to enable shared inspection.
Bedrock calls are gated by sponsor approval; `make bedrock-smoke` requires explicit model configuration and approval.
No model or review-posting call occurs in the Week 1 ingress or stub.
