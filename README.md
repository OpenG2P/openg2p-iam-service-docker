# openg2p-iam-service-docker

Docker creation files and scripts for IAM APIs.

- `scripts/build.sh`: local CLI equivalent of the GitHub Actions docker build workflow
- `test/local_build.py`: lightweight local build helper for a single service spec
- Service specs live under each API directory and drive image name plus dependency versions
- GitHub Actions requires a version like `1.0` or `v1.0.0` and builds all three IAM API specs for that version
