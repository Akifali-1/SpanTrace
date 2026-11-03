"""Verify that the worker image cannot make an outbound HTTP request."""

from __future__ import annotations

import shutil
import subprocess
import sys


IMAGE = "spantrace-worker:0.1.0"


def main() -> int:
    if shutil.which("docker") is None:
        print("Docker CLI unavailable; isolation check not run.")
        return 2
    image = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, text=True, check=False)
    if image.returncode != 0:
        print(f"Worker image {IMAGE} unavailable; isolation check not run.")
        return 2
    code = (
        "import urllib.request; "
        "opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); "
        "opener.open('http://1.1.1.1', timeout=2)"
    )
    command = [
        "docker", "run", "--rm",
        "--user", "1000:1000", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=64",
        "--memory=256m", "--cpus=1.0", "--network", "none",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--entrypoint", "python", IMAGE, "-c", code,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=15)
    if result.returncode == 0:
        print("Outbound HTTP unexpectedly succeeded.")
        return 1
    print("Worker network isolation passed: outbound HTTP failed as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
