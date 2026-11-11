"""Register the nightly memory sync (21:30 local). It commits and pushes memory/ and README.md only."""

import os
import plistlib
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LABEL = "com.ozgurguler.python-fde-memory-sync"
LOGS = Path.home() / "Library/Application Support/PythonFDECoach"


def main():
    path = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    data = {
        "Label": LABEL,
        "ProgramArguments": [
            "/opt/homebrew/bin/python3",
            str(REPO / "tools/sync.py"),
            "--commit",
            "--push",
        ],
        "StartCalendarInterval": {"Hour": 21, "Minute": 30},
        "ProcessType": "Background",
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/bin:/bin"},
        "StandardOutPath": str(LOGS / "memory-sync.log"),
        "StandardErrorPath": str(LOGS / "memory-sync-error.log"),
    }
    path.write_bytes(plistlib.dumps(data))
    path.chmod(0o600)
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True, check=False
    )
    subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
    print(path)


if __name__ == "__main__":
    main()
