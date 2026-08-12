#!/usr/bin/env python3
"""Fetch this repo tarball and exec a module (onboard|watch)."""
from __future__ import annotations

import io
import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path


def main() -> None:
    module = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MALLABOT_MODULE", "mallabot.onboard")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    url = "https://api.github.com/repos/jseramn/mallanet-discord-bots/tarball/main"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mallabot-deploy",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    root = Path("/tmp/mallabot-src")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(root)
    inner = next(p for p in root.iterdir() if p.is_dir())
    app = Path("/app")
    if app.exists():
        shutil.rmtree(app)
    shutil.copytree(inner, app)
    os.chdir(app)
    # install deps then exec
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"])
    os.execv(sys.executable, [sys.executable, "-m", module])


if __name__ == "__main__":
    main()
