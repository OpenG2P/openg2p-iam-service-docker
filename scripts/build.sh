#!/usr/bin/env bash
# =============================================================================
# build.sh — Local CLI equivalent of the docker-build.yml GitHub Actions workflow
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PUSH="${PUSH:-0}"
NO_CACHE="${NO_CACHE:-0}"
BUILD_PLATFORM="${BUILD_PLATFORM:-linux/amd64}"
OVERRIDE_DOCKERFILE=""

DEFAULT_SERVICES=(
  "iam-staff-portal-api/1.0.txt"
  "iam-agent-portal-api/1.0.txt"
  "iam-bene-portal-api/1.0.txt"
)

log()  { echo "[build.sh] $*"; }
err()  { echo "[build.sh] ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  ./build.sh [OPTIONS] [SERVICE_FILE]

Examples:
  ./build.sh
  ./build.sh iam-staff-portal-api/1.0.txt
  ./build.sh --push iam-agent-portal-api/v1.0.0.txt
  ./build.sh --dockerfile iam-bene-portal-api/Dockerfile iam-bene-portal-api/1.0.txt

Required env vars for push:
  DOCKER_HUB_USERNAME
  DOCKER_HUB_TOKEN
EOF
}

cleanup() {
  rm -f "${SCRIPT_DIR}/_service_env.sh"
  rm -f "${REPO_ROOT}/adapters.requirements.txt"
  find "${REPO_ROOT}/local_deps" -mindepth 1 -maxdepth 1 \
    -not -name ".*" -exec rm -rf {} +
}

POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)        usage; exit 0 ;;
    --push)           PUSH=1; shift ;;
    --no-cache)       NO_CACHE=1; shift ;;
    --platform)       BUILD_PLATFORM="$2"; shift 2 ;;
    --dockerfile)     OVERRIDE_DOCKERFILE="$2"; shift 2 ;;
    *)                POSITIONAL+=("$1"); shift ;;
  esac
done

SERVICE_FILES=()
if [[ ${#POSITIONAL[@]} -eq 0 || "${POSITIONAL[0]:-}" == "all" ]]; then
  SERVICE_FILES=("${DEFAULT_SERVICES[@]}")
else
  SERVICE_FILES=("${POSITIONAL[@]}")
fi

if [[ "${PUSH}" == "1" ]]; then
  ENV_FILE="${SCRIPT_DIR}/.env"
  if [[ -f "${ENV_FILE}" ]]; then
    log "Loading credentials from ${ENV_FILE}"
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
  [[ -n "${DOCKER_HUB_USERNAME:-}" ]] || die "DOCKER_HUB_USERNAME is not set."
  [[ -n "${DOCKER_HUB_TOKEN:-}" ]] || die "DOCKER_HUB_TOKEN is not set."

  log "Logging in to Docker Hub as ${DOCKER_HUB_USERNAME}..."
  echo "${DOCKER_HUB_TOKEN}" | docker login --username "${DOCKER_HUB_USERNAME}" --password-stdin
fi

if [[ "${BUILD_PLATFORM}" == *","* ]]; then
  log "Multi-arch build requested (${BUILD_PLATFORM}). Setting up buildx builder..."
  if ! docker buildx inspect openg2p-builder &>/dev/null; then
    docker buildx create --name openg2p-builder --use
  else
    docker buildx use openg2p-builder
  fi
  docker buildx inspect --bootstrap
  BUILDX=1
else
  BUILDX=0
fi

FAILURES=()

for SERVICE_FILE in "${SERVICE_FILES[@]}"; do
  if [[ ! "${SERVICE_FILE}" = /* ]]; then
    SERVICE_FILE="${REPO_ROOT}/${SERVICE_FILE}"
  fi

  log "============================================================"
  log "Processing service file: ${SERVICE_FILE}"
  log "============================================================"

  mkdir -p "${REPO_ROOT}/local_deps"

  python3 "${SCRIPT_DIR}/parse_service.py" \
    --service-file "${SERVICE_FILE}" \
    --repo-root "${REPO_ROOT}" \
    ${OVERRIDE_DOCKERFILE:+--dockerfile "${OVERRIDE_DOCKERFILE}"} \
    --output-env "${SCRIPT_DIR}/_service_env.sh"

  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/_service_env.sh"

  log "Image      : ${SVC_IMAGE}"
  log "Dockerfile : ${SVC_DOCKERFILE}"
  log "Context    : ${SVC_CONTEXT}"
  log "REPO_URL   : ${SVC_REPO_URL}"
  log "GIT_BRANCH : ${SVC_GIT_BRANCH}"

  LOCAL_PKGS=$(find "${REPO_ROOT}/local_deps" -mindepth 1 -maxdepth 1 -not -name ".*" -type d 2>/dev/null || true)
  if [[ -n "${LOCAL_PKGS}" ]]; then
    log "Local deps staged into build context:"
    echo "${LOCAL_PKGS}" | xargs -I{} basename {} | sed 's/^/    /'
  fi

  log "Generated adapters.requirements.txt:"
  cat "${REPO_ROOT}/adapters.requirements.txt"
  echo ""

  BUILD_ARGS=(
    -f "${SVC_DOCKERFILE}"
    -t "${SVC_IMAGE}"
    --build-arg "REPO_URL=${SVC_REPO_URL}"
    --build-arg "GIT_BRANCH=${SVC_GIT_BRANCH}"
    --label "org.opencontainers.image.created=${SVC_CREATED}"
    --label "org.opencontainers.image.revision=${SVC_COMMIT}"
    --label "org.opencontainers.image.vendor=${SVC_VENDOR}"
    --label "org.opencontainers.image.title=${SVC_TITLE}"
    --label "org.opencontainers.image.version=${SVC_VERSION}"
    --label "org.opencontainers.image.description=OpenG2P IAM service image"
  )

  [[ "${NO_CACHE}" == "1" ]] && BUILD_ARGS+=(--no-cache)

  if [[ "${BUILDX}" == "1" ]]; then
    PUSH_FLAG="--load"
    [[ "${PUSH}" == "1" ]] && PUSH_FLAG="--push"
    log "Running: docker buildx build --platform ${BUILD_PLATFORM} ${PUSH_FLAG} ..."
    if docker buildx build \
      --platform "${BUILD_PLATFORM}" \
      "${BUILD_ARGS[@]}" \
      ${PUSH_FLAG} \
      "${SVC_CONTEXT}"; then
      log "Build succeeded: ${SVC_IMAGE}"
    else
      err "Build failed: ${SVC_IMAGE}"
      FAILURES+=("${SVC_IMAGE}")
    fi
  else
    log "Running: docker build ..."
    if docker build "${BUILD_ARGS[@]}" "${SVC_CONTEXT}"; then
      log "Build succeeded: ${SVC_IMAGE}"
      if [[ "${PUSH}" == "1" ]]; then
        log "Pushing ${SVC_IMAGE}..."
        docker push "${SVC_IMAGE}"
      fi
    else
      err "Build failed: ${SVC_IMAGE}"
      FAILURES+=("${SVC_IMAGE}")
    fi
  fi

  cleanup
done

echo ""
log "============================================================"
log "Build Summary"
log "============================================================"
TOTAL=${#SERVICE_FILES[@]}
FAILED=${#FAILURES[@]}
PASSED=$(( TOTAL - FAILED ))
log "Total: ${TOTAL}  Passed: ${PASSED}  Failed: ${FAILED}"

if [[ ${FAILED} -gt 0 ]]; then
  err "The following builds failed:"
  for f in "${FAILURES[@]}"; do
    err "  - ${f}"
  done
  exit 1
fi

log "All builds completed successfully."
