"""Register a private Safari portal opening at 15:00 in the Mac calendar timezone.

launchd calendar triggers use the system timezone; TZ controls the child process
only. Keep the Mac timezone Europe/Istanbul to match the requested schedule.
The agent runs when logged in; missed sleep-time calendar events may run on wake.
"""

import argparse
import os
import plistlib
import subprocess
from pathlib import Path

LABEL = "com.ozgurguler.python-fde-portal"
TARGET = Path.home() / ".codex/skills/python-fde-email-coach"
ROOT = Path.home() / "Library/Application Support/PythonFDECoach"


def configuration(skill, root):
    return {
        "Label": LABEL,
        "ProgramArguments": [
            "/opt/homebrew/bin/python3",
            str(skill / "scripts/portal.py"),
            "open",
            "--root",
            str(root),
        ],
        "StartCalendarInterval": {"Hour": 15, "Minute": 0},
        "ProcessType": "Background",
        "Umask": 63,
        "EnvironmentVariables": {"TZ": "Europe/Istanbul", "PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(root / "portal-launch.log"),
        "StandardErrorPath": str(root / "portal-launch-error.log"),
    }


def install(root=ROOT, skill=TARGET):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(configuration(skill, root)))
    path.chmod(0o600)
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", domain + "/" + LABEL], capture_output=True, check=False
    )
    subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skill", type=Path, default=TARGET)
    args = parser.parse_args()
    print(install(args.root, args.skill))


if __name__ == "__main__":
    main()
