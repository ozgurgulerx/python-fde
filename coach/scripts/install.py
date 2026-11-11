"""Install the already authorized private coach and register its schedule; never send."""

import os, plistlib, shutil, subprocess
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
TARGET = Path.home() / ".codex/skills/python-fde-email-coach"
LABEL = "com.ozgurguler.python-fde-email-coach"


def main():
    if SOURCE != TARGET:
        shutil.copytree(
            SOURCE,
            TARGET,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", ".coverage"),
        )
    root = Path.home() / "Library/Application Support/PythonFDECoach"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    data = {
        "Label": LABEL,
        "ProgramArguments": [
            "/opt/homebrew/bin/python3",
            str(TARGET / "scripts/coach.py"),
            "tick",
        ],
        "StartInterval": 900,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "Umask": 63,
        "EnvironmentVariables": {
            "PATH": "/Users/ozgurguler/.nvm/versions/node/v22.23.2/bin:/opt/homebrew/bin:/usr/bin:/bin",
            "PYTHONUNBUFFERED": "1",
        },
        "StandardOutPath": str(root / "launchd.log"),
        "StandardErrorPath": str(root / "launchd-error.log"),
    }
    path.write_bytes(plistlib.dumps(data))
    path.chmod(0o600)
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", domain + "/" + LABEL], capture_output=True, check=False
    )
    subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
    print(path)


if __name__ == "__main__":
    main()
