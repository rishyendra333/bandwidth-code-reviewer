# Installation and shared AWS runbook

## 1. Accounts and permissions

The shared development stack lives in **516647891652 / us-west-2**. The deployment owner uses AWS profile `default`.
Record each teammate's account ID and exact IAM user ARN. Their account credentials do not automatically authorize access to the shared account.

Ask the Bandwidth administrator for:

- `SignInLocalDevelopmentAccess` on IAM identities using browser CLI login.
- Owner provisioning permissions for project S3, Lambda, API Gateway v2, SQS, DynamoDB, Secrets Manager, CloudWatch Logs, and IAM roles/policies; include `iam:PassRole` scoped to the runtime role and the required permissions boundary, if any.
- Owner state-bucket permissions: list the bucket, get/put state objects, and get/put/delete the `.tflock` objects. Bucket bootstrap also requires configuring versioning, encryption, blocking public access, and bucket policy.
- Teammate `sts:AssumeRole` permission on `arn:aws:iam::516647891652:role/bandwidth-reviewer-dev-inspect` in their own accounts.
- Approved Bedrock model/profile, permitted inference destinations, model invocation permissions, account use-case registration, and quotas.

Terraform creates the inspection role only when `teammate_user_arns` contains approved identities. Empty input leaves it disabled. Access is a prerequisite; never broaden trust to an entire account to bypass missing identities.
Some CloudWatch listing/query-result/metric actions require wildcard resources; they expose read-only account metadata. Table data, log contents, Lambda/API configuration, and queue configuration are restricted to the project. The role cannot read secrets or state, invoke Lambda, receive/delete queue messages, or mutate tables.

## 2. Laptop authentication

Install AWS CLI >=2.32, Python 3.12/uv, Terraform >=1.10,<2, Docker Desktop, Node >=20, git, and ripgrep.
The owner can retain the existing `default` profile. Verify it returns the agreed account:

```sh
aws sts get-caller-identity --profile default
```

For a teammate with IAM console credentials and CLI-login permission:

```sh
aws configure set region us-west-2 --profile bandwidth-console
aws login --profile bandwidth-console
aws sts get-caller-identity --profile bandwidth-console
```

Add this compatibility profile to the standard AWS config file:

```ini
[profile bandwidth-dev]
region = us-west-2
credential_process = aws configure export-credentials --profile bandwidth-console --format process
```

Set the appropriate `AWS_PROFILE` in ignored `.env`. Never put credentials or console passwords into Terraform variables or Git.

After the owner supplies the role, teammates can use its Terraform output switch-role URL in the console, or configure:

```ini
[profile bandwidth-inspect]
role_arn = arn:aws:iam::516647891652:role/bandwidth-reviewer-dev-inspect
source_profile = bandwidth-dev
region = us-west-2
```

Verify `aws sts get-caller-identity --profile bandwidth-inspect`; its account should be 516647891652.

## 3. GitHub Apps

Check availability of `bandwidth-reviewer` and `bandwidth-reviewer-dev`, and whether the GitHub user `bandwidth-reviewer` exists. Resolve a collision with Bandwidth before registering the shared app. The configured trigger can be changed to match an approved name.

The shared app [bandwidth-reviewer-dev](https://github.com/apps/bandwidth-reviewer-dev) is registered under **AlexShen12**, App ID **5109565**, with ownership handoff planned. The shared sandbox is [rishyendra333/bandwidth-reviewer-demo](https://github.com/rishyendra333/bandwidth-reviewer-demo).
Its repository owner must install the app and select only `bandwidth-reviewer-demo`; AlexShen12 currently has read-only repository access. Every developer creates `bandwidth-reviewer-dev-<name>` under their own GitHub account and installs it on their personal sandbox.

Repository permissions:

| Permission | Access | Purpose |
|---|---|---|
| Pull requests | Read/write | Future PR collection and advisory reviews |
| Contents | Read | Future config and repository context |
| Issues | Read/write | PR-comment commands, reactions, replies |
| Checks | Read/write | Future review progress check |
| Metadata | Read | GitHub repository identification |

Subscribe to `issue_comment`; automatic installation events are also recorded. Enable webhooks and configure a random webhook secret. Generate the app private key.

For personal apps, create a unique smee channel, set it as the app webhook URL, and put `SMEE_URL`, `WEBHOOK_SECRET`, and the exact personal `TRIGGER` in `.env`. Store the private key under `.secrets/` and set `GITHUB_PRIVATE_KEY_PATH` for Milestone 2. Personal secrets stay local.

`make dev` runs Moto, ingress, a fake worker, and optional smee on localhost. Use team-controlled public sandbox data through the relay; sponsor repository data requires an approved forwarding arrangement. With no relay configured, `make e2e` still proves the complete local HTTP path.

The shared app will use Terraform's `webhook_url`, not a teammate's smee channel.

## 4. Bootstrap Terraform state (owner)

Copy `.env.example` to `.env`, set `AWS_PROFILE=default` and `HOSTING_ACCOUNT_ID=516647891652`.
Commit the reviewed implementation before planning so saved plans can be tied to an exact commit. Docker Desktop must be running for the application package build.

```sh
make bootstrap
# Review the saved bootstrap plan displayed by Terraform.
make bootstrap-apply
# Confirm the state-migration prompt after the initial bucket creation.
cp infra/dev/dev.tfvars.example infra/dev/dev.tfvars
```

Bootstrap creates `bandwidth-reviewer-tfstate-516647891652-us-west-2` with encryption, versioning, public-access blocking, and TLS-only access. Initial state is local; `bootstrap-apply` creates an ignored backend declaration and migrates it into `bootstrap/terraform.tfstate` in that bucket. Retain the local backup until remote state is verified.

The application uses `dev/terraform.tfstate`; both use native S3 locking (`use_lockfile=true`). Backend credentials come from AWS profiles. `allowed_account_ids` protects both backend and provider.

Add approved teammate IAM user ARNs and any required role permissions boundary to ignored `infra/dev/dev.tfvars`. Empty teammate input is valid for initial deployment but shared-inspection acceptance remains pending.

## 5. Plan, apply, and populate secrets (owner)

```sh
make plan
# Inspect the saved Terraform plan. Review again if the commit or artifact changes.
make deploy
```

`make plan` verifies the caller account, builds the Lambda ZIP inside Linux x86_64 Python 3.12 Docker, initializes the remote backend, validates HCL, and saves the plan plus a commit/artifact receipt.
`make deploy` verifies that receipt before applying the saved plan. It writes non-secret identifiers to `.build/outputs.json` and a commit-linked deployment record to `.build/deployment.json`.

Both Secrets Manager resources are initially empty. Populate the shared webhook secret and the app PEM private key **directly in Secrets Manager**, using its console. Terraform never reads or manages secret versions. Select a randomly generated webhook secret of at least 32 bytes and copy the same value into the shared GitHub App settings. Do not store secret contents in state, plan files, shell command arguments, or logs.

For the initial shared deployment, both secret values have already been populated outside Terraform. The private key was checked against GitHub's App identity before storage. See [WEEK1.md](WEEK1.md) for deployment evidence and outstanding acceptance steps.

Set the shared GitHub App's webhook URL to the output `webhook_url`. Verify its ping delivery receives 200 after the webhook secret is populated.

```sh
make outputs
make e2e MODE=aws
```

The AWS smoke test uses a signed synthetic webhook, verifies the DynamoDB record and exactly one matching SQS job, and deletes only its own test message. Run it before connecting a live worker. Queue reads change receive counts; teammates inspect queue attributes/metrics rather than consuming messages.

Finally comment the configured trigger on an actual sandbox PR. Confirm the GitHub delivery, DynamoDB record, SQS message, and CloudWatch log share the delivery ID. This separate GitHub demo confirms installation and connectivity.

## 6. Delivery recovery

Completed deliveries are acknowledged as duplicates. Pending claims have a 30-second lease. Active pending deliveries return 503; after expiration a redelivery can take over. A failed enqueue releases its claim for immediate redelivery when possible.

GitHub does not automatically retry failed webhook deliveries. Use the app's Recent deliveries → Redeliver after resolving the error. After a timeout/crash, wait at least 30 seconds before redelivery.

A crash after SQS accepts but before DynamoDB marks queued can produce two jobs with the same `delivery_id`. SQS itself also has at-least-once delivery. The Milestone 2 worker must implement delivery/run idempotency before real review posting is enabled.

Logs contain fixed outcomes, timing, delivery IDs, and message IDs—not request bodies, signatures, private keys, arguments, or exception details. Secrets are cached for five minutes; after webhook-secret rotation allow the cache to expire or redeploy/recycle ingress before testing the new value.

## 7. Bedrock approval gate

Week 1 local execution is always fake. `BEDROCK=real` fails with an explanation rather than enabling unimplemented review calls.
After Bandwidth approves the model and its destinations, record that decision in the team setup record, configure `BEDROCK_APPROVED=true` and `BEDROCK_MODEL_ID` in ignored `.env`, ensure the account prerequisites and IAM permissions are satisfied, and run:

```sh
make bedrock-smoke
```

This sends only `Reply with OK.` through Converse and reports token usage. It sends no repository code. US cross-region inference requires invocation permission for the profile and each destination model; the source region `us-west-2` alone does not guarantee Oregon-only processing.
