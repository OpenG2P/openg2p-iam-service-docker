#!/usr/bin/env python3
"""
Parse an IAM service spec file and emit a shell-sourceable env file plus the
adapters.requirements.txt consumed by the Dockerfiles.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def _is_local_path(val: str) -> bool:
    return val.startswith("/") or val.startswith("./") or val.startswith("../")


def _resolve_local_dep(val: str, repo_root: str) -> tuple[str, str]:
    src = os.path.abspath(val.strip())
    pkg_name = os.path.basename(src)
    local_deps_root = os.path.join(repo_root, "local_deps")
    dest = os.path.join(local_deps_root, pkg_name)

    if not os.path.exists(src):
        print(f"ERROR: Local dependency path does not exist: {src}", file=sys.stderr)
        sys.exit(1)

    if os.path.exists(dest):
        shutil.rmtree(dest)
    print(f"  [local] Copying {src}  ->  local_deps/{pkg_name}/")
    shutil.copytree(src, dest)

    return f"./local_deps/{pkg_name}", pkg_name


def _clean_stale_local_deps(repo_root: str, current_pkgs: list[str]) -> None:
    local_deps_root = os.path.join(repo_root, "local_deps")
    if not os.path.exists(local_deps_root):
        return
    for entry in os.listdir(local_deps_root):
        if entry.startswith("."):
            continue
        if entry not in current_pkgs:
            stale = os.path.join(local_deps_root, entry)
            if os.path.isdir(stale):
                shutil.rmtree(stale)
                print(f"  [local] Removed stale local_deps/{entry}/")


def parse_service_file(service_file: str, override_dockerfile: str | None, repo_root: str) -> dict:
    service_file = os.path.abspath(service_file)
    if not os.path.exists(service_file):
        print(f"Error: Service file not found: {service_file}", file=sys.stderr)
        sys.exit(1)

    with open(service_file, encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]

    if not lines or not lines[0].startswith("#!"):
        print("Error: Invalid service file format. First line must be '#!IMAGE_ID'", file=sys.stderr)
        sys.exit(1)

    image_id = lines[0].lstrip("#!").strip()
    dockerfile = override_dockerfile or ""

    if not dockerfile:
        service_dir = os.path.dirname(service_file)
        candidate = os.path.join(service_dir, "Dockerfile")
        if os.path.exists(candidate):
            dockerfile = candidate

    if not dockerfile and len(lines) > 1 and lines[1].startswith("#!"):
        dockerfile = lines[1].lstrip("#!").strip()

    if not dockerfile:
        print(
            f"Error: Could not determine Dockerfile for {service_file}. Pass --dockerfile explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)

    local_deps_root = os.path.join(repo_root, "local_deps")
    os.makedirs(local_deps_root, exist_ok=True)

    deps = []
    local_pkgs = []
    repo_url = ""
    git_branch = ""

    for line in lines:
        if line.startswith("#"):
            continue
        val = line.strip()
        if not val:
            continue

        if _is_local_path(val):
            pip_line, pkg_name = _resolve_local_dep(val, repo_root)
            deps.append(pip_line)
            local_pkgs.append(pkg_name)
            continue

        match = re.match(r"git://([^/]+)//(.+)", val)
        if match:
            tag = match.group(1)
            url_full = match.group(2)
            if not repo_url:
                repo_url = url_full.split("#")[0] if "#" in url_full else url_full
                git_branch = tag
            if "#" in url_full:
                base, frag = url_full.split("#", 1)
                deps.append(f"git+{base}@{tag}#{frag}")
            else:
                deps.append(f"git+{url_full}@{tag}")
            continue

        deps.append(val)

    _clean_stale_local_deps(repo_root, local_pkgs)

    req_path = os.path.join(repo_root, "adapters.requirements.txt")
    with open(req_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(deps))
        if deps:
            handle.write("\n")

    print("---- adapters.requirements.txt ----")
    print("\n".join(deps) or "(empty)")
    print("-----------------------------------")
    if local_pkgs:
        print(f"Local packages staged into local_deps/: {', '.join(local_pkgs)}")
    else:
        print("No local packages - local_deps/ is empty (remote-only build).")

    try:
        commit_hash = (
            subprocess.check_output(
                ["git", "--no-pager", "log", "-1", "--pretty=format:%H"],
                cwd=repo_root,
            )
            .decode()
            .strip()
        )
    except Exception:
        commit_hash = "unknown"

    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    vendor = image_id.split("/")[0] if "/" in image_id else "unknown"
    try:
        title = image_id.split("/")[1].split(":")[0]
    except IndexError:
        title = image_id
    version = image_id.split(":")[-1] if ":" in image_id else "latest"

    if not os.path.isabs(dockerfile):
        dockerfile = os.path.join(repo_root, dockerfile)
    dockerfile = os.path.abspath(dockerfile)

    return {
        "SVC_IMAGE": image_id,
        "SVC_DOCKERFILE": dockerfile,
        "SVC_CONTEXT": repo_root,
        "SVC_REPO_URL": repo_url,
        "SVC_GIT_BRANCH": git_branch,
        "SVC_CREATED": created,
        "SVC_COMMIT": commit_hash,
        "SVC_VENDOR": vendor,
        "SVC_TITLE": title,
        "SVC_VERSION": version,
    }


def write_env_file(env_vars: dict, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        for key, value in env_vars.items():
            safe_value = str(value).replace("'", "'\\''")
            handle.write(f"export {key}='{safe_value}'\n")
    print(f"Env written to: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse OpenG2P IAM service spec file.")
    parser.add_argument("--service-file", required=True, help="Path to the service spec file")
    parser.add_argument("--repo-root", required=True, help="Packaging repo root")
    parser.add_argument("--dockerfile", help="Optional Dockerfile override")
    parser.add_argument("--output-env", required=True, help="Where to write exported shell variables")
    args = parser.parse_args()

    env_vars = parse_service_file(args.service_file, args.dockerfile, args.repo_root)
    write_env_file(env_vars, args.output_env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
