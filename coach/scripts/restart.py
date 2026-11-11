"""Explicit user-authorized fresh course; preserve the prior ledger and audits."""

import argparse
import fcntl
import json
import re
import shutil
import tempfile
from pathlib import Path

import coach


def _snapshot(root, destination, previous, restart_id, timestamp):
    for source in root.iterdir():
        if source.name in ("history", "portal", ".lock", ".restart-staging"):
            continue
        target = destination / source.name
        if source.is_dir():
            shutil.copytree(source, target, symlinks=True)
        else:
            shutil.copy2(source, target, follow_symlinks=False)
    coach.write(destination / "state.json", previous)
    coach.write(
        destination / "restart.json",
        {
            "restart_id": restart_id,
            "at": timestamp,
            "status": "snapshotted",
            "authorization": "User explicitly requested start from scratch and retain a portal of sent lessons.",
            "previous_pending_retained": bool(previous.get("pending")),
        },
    )


def restart(root, restart_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", restart_id):
        raise ValueError(
            "restart-id must contain 1–80 letters, digits, underscores or hyphens"
        )
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = coach.load(root)
        if current.get("restart_id") == restart_id:
            return {
                "status": "already_restarted",
                "archive": current["previous_course_archive"],
            }
        history = root / "history"
        history.mkdir(exist_ok=True, mode=0o700)
        matches = list(history.glob("*--" + restart_id))
        if matches:
            archive = matches[0]
            metadata = json.loads((archive / "restart.json").read_text())
            if metadata["status"] == "complete":
                return {"status": "already_restarted", "archive": str(archive)}
            previous = json.loads((archive / "state.json").read_text())
            timestamp = metadata["at"]
        else:
            now = coach.local()
            timestamp = now.isoformat()
            archive = history / (now.strftime("%Y%m%dT%H%M%S%f") + "--" + restart_id)
            previous = current
            staging = root / ".restart-staging"
            staging.mkdir(exist_ok=True, mode=0o700)
            with tempfile.TemporaryDirectory(prefix="snapshot-", dir=staging) as temp:
                temporary = Path(temp)
                _snapshot(root, temporary, previous, restart_id, timestamp)
                temporary.rename(archive)
        fresh = {
            **coach.initial(),
            "frequency": previous.get("frequency", [6, 6]),
            "course": "Python from scratch",
            "restarted_at": timestamp,
            "restart_id": restart_id,
            "previous_course_archive": str(archive),
        }
        coach.save(root, fresh)
        metadata = json.loads((archive / "restart.json").read_text())
        coach.write(archive / "restart.json", {**metadata, "status": "complete"})
        return {"status": "restarted", "archive": str(archive), "at": timestamp}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=coach.ROOT)
    parser.add_argument("--restart-id", required=True)
    args = parser.parse_args()
    print(json.dumps(restart(args.root, args.restart_id)))


if __name__ == "__main__":
    main()
