# =============================================================================
# scripts/README.md — Local build scripts for openg2p-iam-service-docker
# =============================================================================

## Overview

The `scripts/` folder provides a fully local, command-line equivalent of the
GitHub Actions Docker build workflow.

Running `build.sh` does the following:

1. Reads an IAM service spec file such as `iam-staff-portal-api/1.0.txt`
2. Parses the Docker image tag, git dependencies, and Dockerfile path
3. Generates `adapters.requirements.txt` in the repo root
4. Runs `docker build` with OCI labels and build args
5. Optionally pushes to Docker Hub

For the GitHub Actions workflow, the required `version` input accepts values
such as `1.0` or `v1.0.0`. That expands to all three API specs for that
version.

## Files

- `build.sh`: main entry point
- `parse_service.py`: helper that parses service spec files
- `.env.example`: template for Docker Hub credentials
- `README.md`: this file

## Quick Start

```bash
cp scripts/.env.example scripts/.env
chmod +x scripts/build.sh
./scripts/build.sh
./scripts/build.sh iam-staff-portal-api/1.0.txt
./scripts/build.sh --push iam-agent-portal-api/v1.0.0.txt
```

## Service Spec File Format

```text
#!docker-org/image-name:tag
git://BRANCH_OR_TAG//GITHUB_URL#subdirectory=pkg
regular-pypi-package==1.0.0
```

The script converts each `git://` line into a pip-installable URL and writes
them into `adapters.requirements.txt`, which the Dockerfiles install.

Dockerfile resolution order:

1. `--dockerfile` CLI argument
2. `Dockerfile` in the same directory as the spec file
3. a second `#!` line in the spec file

## Default Service Matrix

When called with no arguments, `build.sh` builds:

- `iam-staff-portal-api/1.0.txt`
- `iam-agent-portal-api/1.0.txt`
- `iam-bene-portal-api/1.0.txt`
