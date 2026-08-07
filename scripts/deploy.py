#!/usr/bin/env python3
"""
Qoresence Deployment Script — Phase 9

Automates building and deploying Qoresence to various environments.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str], cwd: Path = None, env: dict = None) -> subprocess.CompletedProcess:
    """Run command and return result."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result


def build_docker(tag: str = "qoresence:latest", no_cache: bool = False) -> bool:
    """Build Docker image."""
    cmd = ["docker", "build", "-t", tag, "."]
    if no_cache:
        cmd.insert(2, "--no-cache")
    result = run_cmd(cmd)
    return result.returncode == 0


def push_docker(tag: str, registry: str = None) -> bool:
    """Push Docker image to registry."""
    if registry:
        full_tag = f"{registry}/{tag}"
        run_cmd(["docker", "tag", tag, full_tag])
        tag = full_tag
    result = run_cmd(["docker", "push", tag])
    return result.returncode == 0


def run_container(
    image: str = "qoresence:latest",
    env_file: str = None,
    detach: bool = True,
    ports: list[str] = None,
    volumes: list[str] = None,
    devices: list[str] = None,
    command: list[str] = None,
) -> bool:
    """Run Docker container."""
    cmd = ["docker", "run"]
    if detach:
        cmd.append("-d")
    else:
        cmd.extend(["-it", "--rm"])

    if env_file:
        cmd.extend(["--env-file", env_file])

    if ports:
        for p in ports:
            cmd.extend(["-p", p])

    if volumes:
        for v in volumes:
            cmd.extend(["-v", v])

    if devices:
        for d in devices:
            cmd.extend(["--device", d])

    cmd.append(image)

    if command:
        cmd.extend(command)

    result = run_cmd(cmd)
    return result.returncode == 0


def deploy_compose(env_file: str = None, detach: bool = True) -> bool:
    """Deploy using docker-compose."""
    cmd = ["docker-compose"]
    if env_file:
        os.environ["COMPOSE_FILE"] = "docker-compose.yml"
    cmd.extend(["up"])
    if detach:
        cmd.append("-d")
    else:
        cmd.append("--build")

    result = run_cmd(cmd)
    return result.returncode == 0


def stop_compose() -> bool:
    """Stop docker-compose deployment."""
    result = run_cmd(["docker-compose", "down"])
    return result.returncode == 0


def health_check(container_name: str = "qoresence") -> bool:
    """Check container health."""
    result = run_cmd(["docker", "inspect", "--format={{.State.Health.Status}}", container_name])
    if result.returncode == 0:
        status = result.stdout.strip()
        return status == "healthy"
    return False


def main():
    parser = argparse.ArgumentParser(
        prog="deploy.py",
        description="Qoresence deployment automation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Build
    build_parser = subparsers.add_parser("build", help="Build Docker image")
    build_parser.add_argument("--tag", default="qoresence:latest", help="Image tag")
    build_parser.add_argument("--no-cache", action="store_true", help="Build without cache")

    # Push
    push_parser = subparsers.add_parser("push", help="Push Docker image to registry")
    push_parser.add_argument("--tag", default="qoresence:latest", help="Image tag")
    push_parser.add_argument("--registry", help="Registry URL (e.g., ghcr.io/user)")

    # Run
    run_parser = subparsers.add_parser("run", help="Run container")
    run_parser.add_argument("--image", default="qoresence:latest", help="Image to run")
    run_parser.add_argument("--env-file", help="Environment file")
    run_parser.add_argument("--interactive", action="store_true", help="Run interactively")
    run_parser.add_argument("--port", action="append", help="Port mapping (host:container)")
    run_parser.add_argument("--volume", action="append", help="Volume mount (host:container)")
    run_parser.add_argument("--device", action="append", help="Device mount")
    run_parser.add_argument("command", nargs="*", help="Command to run in container")

    # Compose up
    compose_parser = subparsers.add_parser("up", help="Deploy with docker-compose")
    compose_parser.add_argument("--env-file", help="Environment file")
    compose_parser.add_argument("--detach", action="store_true", default=True, help="Run detached")

    # Compose down
    subparsers.add_parser("down", help="Stop docker-compose deployment")

    # Health check
    health_parser = subparsers.add_parser("health", help="Check container health")
    health_parser.add_argument("--container", default="qoresence", help="Container name")

    args = parser.parse_args()

    if args.command == "build":
        success = build_docker(args.tag, args.no_cache)
    elif args.command == "push":
        success = push_docker(args.tag, args.registry)
    elif args.command == "run":
        success = run_container(
            args.image,
            args.env_file,
            not args.interactive,
            args.port,
            args.volume,
            args.device,
            args.command,
        )
    elif args.command == "up":
        success = deploy_compose(args.env_file, args.detach)
    elif args.command == "down":
        success = stop_compose()
    elif args.command == "health":
        success = health_check(args.container)
    else:
        parser.print_help()
        return 1

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
