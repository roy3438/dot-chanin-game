"""Locate a checkpoint from the same workflow and verify the downloaded bytes."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path]))


def digest(folder):
    return hashlib.sha256((folder / "candidate.json").read_bytes()).hexdigest()


def seal(folder):
    (folder / "digest.txt").write_text(digest(folder) + "\n", encoding="ascii")


def restore(folder, name, require_match=False):
    repo = os.environ["GITHUB_REPOSITORY"]
    event = os.environ["GITHUB_EVENT_NAME"]
    revision = os.environ["GITHUB_SHA"]
    if event == "pull_request":
        payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        revision = payload["pull_request"]["head"]["sha"]
    workflow = os.environ["GITHUB_WORKFLOW_REF"].split("@", 1)[0].removeprefix(repo + "/")
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,180}", name):
        raise ValueError("Invalid checkpoint name")
    page = 1
    while True:
        items = api(f"repos/{repo}/actions/artifacts?name={name}&per_page=100&page={page}")["artifacts"]
        for item in sorted(items, key=lambda entry: entry["id"], reverse=True):
            if item["expired"] or item["name"] != name:
                continue
            run_id = item["workflow_run"]["id"]
            run = api(f"repos/{repo}/actions/runs/{run_id}")
            if (run["event"] != event or run["path"] != workflow or run["head_sha"] != revision
                    or run["head_repository"]["id"] != int(os.environ["GITHUB_REPOSITORY_ID"])):
                continue
            with tempfile.TemporaryDirectory() as temp:
                subprocess.run(["gh", "run", "download", str(run_id), "--repo", repo,
                                "--name", name, "--dir", temp], check=True)
                source = Path(temp)
                expected = (source / "digest.txt").read_text(encoding="ascii").strip()
                if digest(source) != expected:
                    raise ValueError("Checkpoint digest mismatch")
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "candidate.json").write_bytes((source / "candidate.json").read_bytes())
                print(f"Verified checkpoint from run {run_id}: {expected}")
                return
        if len(items) < 100:
            break
        page += 1
    if require_match:
        raise ValueError("Expected checkpoint missing")
    print("No matching checkpoint")


if __name__ == "__main__":
    folder = Path(os.environ["STUDIO_CHECKPOINT"])
    if sys.argv[1] == "seal":
        seal(folder)
    elif sys.argv[1] == "restore":
        restore(folder, os.environ["CHECKPOINT_NAME"], "--required" in sys.argv[2:])
    else:
        raise SystemExit("Unknown checkpoint operation")
