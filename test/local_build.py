#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


def parse_service_file(service_file, override_dockerfile=None):
    if not os.path.exists(service_file):
        print(f"Error: Service file not found: {service_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading service file: {service_file}")
    with open(service_file, encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]

    if not lines or not lines[0].startswith("#!"):
        print("Error: Invalid file format. First line must start with #!IMAGE_ID", file=sys.stderr)
        sys.exit(1)

    image_id = lines[0].lstrip("#!").strip()
    print(f"Target Image ID: {image_id}")

    dockerfile = override_dockerfile
    if not dockerfile:
        service_dir = os.path.dirname(service_file)
        candidate = os.path.join(service_dir, "Dockerfile")
        if os.path.exists(candidate):
            dockerfile = candidate

    if not dockerfile and len(lines) > 1 and lines[1].startswith("#!"):
        dockerfile = lines[1].lstrip("#!").strip()

    if not dockerfile:
        print("Error: Dockerfile path could not be determined.", file=sys.stderr)
        sys.exit(1)

    print(f"Using Dockerfile: {dockerfile}")

    deps = []
    for line in lines:
        if line.startswith("#"):
            continue
        val = line.strip()
        match = re.match(r"git://([^/]+)//(.+)", val)
        if match:
            tag = match.group(1)
            url_full = match.group(2)
            if "#" in url_full:
                base, frag = url_full.split("#", 1)
                deps.append(f"git+{base}@{tag}#{frag}")
            else:
                deps.append(f"git+{url_full}@{tag}")
        elif val:
            deps.append(val)

    return image_id, dockerfile, deps


def main():
    parser = argparse.ArgumentParser(description="Build OpenG2P IAM Docker image locally using a spec file.")
    parser.add_argument(
        "service_file",
        nargs="?",
        default="iam-staff-portal-api/1.0.txt",
        help="Path to the service spec file",
    )
    parser.add_argument("--dockerfile", help="Path to Dockerfile (optional)")
    parser.add_argument("--push", action="store_true", help="Push image after build")
    parser.add_argument("--no-cache", action="store_true", help="Do not use cache when building")
    args = parser.parse_args()

    image_id, dockerfile, deps = parse_service_file(args.service_file, args.dockerfile)

    req_file = "adapters.requirements.txt"
    with open(req_file, "w", encoding="utf-8") as handle:
        handle.write("\n".join(deps))
        if deps:
            handle.write("\n")

    print(f"\nGenerated {req_file}:")
    print("\n".join(deps))
    print("-" * 30)

    try:
        commit_hash = subprocess.check_output(["git", "--no-pager", "log", "-1", "--pretty=format:%H"]).decode().strip()
    except Exception:
        commit_hash = "unknown"

    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    vendor = image_id.split("/")[0] if "/" in image_id else "unknown"
    try:
        title = image_id.split("/")[1].split(":")[0]
    except IndexError:
        title = image_id
    version = image_id.split(":")[-1] if ":" in image_id else "latest"

    cmd = [
        "docker", "build",
        "-f", dockerfile,
        "-t", image_id,
        "--label", f"org.opencontainers.image.created={created}",
        "--label", f"org.opencontainers.image.revision={commit_hash}",
        "--label", f"org.opencontainers.image.vendor={vendor}",
        "--label", f"org.opencontainers.image.title={title}",
        "--label", f"org.opencontainers.image.version={version}",
        ".",
    ]

    if args.no_cache:
        cmd.insert(2, "--no-cache")

    print(f"\nRunning build command:\n{' '.join(cmd)}\n")
    subprocess.check_call(cmd)
    print(f"\nBuild successful. Image: {image_id}")

    if args.push:
        print(f"Pushing image {image_id}...")
        subprocess.check_call(["docker", "push", image_id])


if __name__ == "__main__":
    main()
