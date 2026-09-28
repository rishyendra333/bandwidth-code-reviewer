# Contributing
1. Clone the repository and install Python 3.12, uv, git, ripgrep, Docker, Node, AWS CLI >=2.32, and Terraform >=1.10,<2.
2. Run `make setup` (`make setup-local` omits the AWS CLI/Terraform prerequisite checks).
3. Copy `.env.example` to ignored `.env`; set your personal app trigger and webhook secret.
4. Register/install your personal GitHub App and set its smee channel as described in [INSTALL.md](INSTALL.md).
5. Run `make dev`; with `SMEE_URL` configured it forwards webhooks automatically.
6. Run `make test`, `make e2e`, and `make lint` before submitting a change.
7. Keep secrets, private keys, Terraform state, saved plans, and local variables in ignored files.
8. Submit changes for review; the deployment owner applies the reviewed commit to shared AWS.
