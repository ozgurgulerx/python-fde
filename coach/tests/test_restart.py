import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import coach
import restart
import install_portal


class RestartTests(unittest.TestCase):
    def test_preserves_pending_and_artifacts_then_clears_new_course(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = {
                **coach.initial(),
                "frequency": [6, 6],
                "pending": {"token": "frozen", "attempted_at": "date"},
                "sent": [{"message_id": "id"}],
            }
            coach.save(root, old)
            (root / "mail").mkdir()
            (root / "mail" / "receipt.json").write_text('{"sent": false}')
            result = restart.restart(root, "user-20261111")
            backup = Path(result["archive"])
            self.assertEqual(json.loads((backup / "state.json").read_text()), old)
            self.assertEqual(
                (backup / "mail" / "receipt.json").read_text(), '{"sent": false}'
            )
            current = coach.load(root)
            self.assertIsNone(current["pending"])
            self.assertEqual(current["sent"], [])
            self.assertEqual(current["frequency"], [6, 6])
            self.assertEqual(current["course"], "Python from scratch")
            self.assertEqual(result["status"], "restarted")
            self.assertEqual((root / "state.json").stat().st_mode & 0o777, 0o600)

    def test_idempotency_does_not_clear_new_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            restart.restart(root, "once")
            state = {**coach.load(root), "topics": {"new": "learning"}}
            coach.save(root, state)
            result = restart.restart(root, "once")
            self.assertEqual(result["status"], "already_restarted")
            self.assertEqual(coach.load(root), state)
            self.assertEqual(len(list((root / "history").iterdir())), 1)

    def test_invalid_id_and_existing_history_not_recopied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                restart.restart(root, "../escape")
            restart.restart(root, "first")
            result = restart.restart(root, "second")
            self.assertFalse((Path(result["archive"]) / "history").exists())

    def test_interrupted_snapshot_is_invisible_and_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = {**coach.initial(), "frequency": [6, 6], "pending": {"token": "keep"}}
            coach.save(root, old)
            with patch.object(
                restart.shutil, "copy2", side_effect=OSError("interrupted")
            ):
                with self.assertRaises(OSError):
                    restart.restart(root, "retry")
            self.assertEqual(coach.load(root), old)
            self.assertEqual(list((root / "history").glob("*/state.json")), [])
            self.assertEqual(list((root / "history").glob("*--retry")), [])
            result = restart.restart(root, "retry")
            self.assertEqual(result["status"], "restarted")
            self.assertEqual(
                json.loads((Path(result["archive"]) / "state.json").read_text()), old
            )
            self.assertFalse((Path(result["archive"]) / ".restart-staging").exists())

    def test_installer_registers_written_plist(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / "coach"
            skill = home / "skill"
            with patch.object(
                install_portal.Path, "home", return_value=home
            ), patch.object(install_portal.subprocess, "run") as run:
                path = install_portal.install(root, skill)
            self.assertEqual(
                plistlib.loads(path.read_bytes()),
                install_portal.configuration(skill, root),
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[0][1], "bootout")
            self.assertEqual(run.call_args_list[1].args[0][1], "bootstrap")
            self.assertTrue(run.call_args_list[1].kwargs["check"])

    def test_calendar_launches_portal_without_run_at_load(self):
        data = install_portal.configuration(Path("/test/skill"), Path("/test/root"))
        self.assertEqual(data["StartCalendarInterval"], {"Hour": 15, "Minute": 0})
        self.assertEqual(
            data["ProgramArguments"],
            [
                "/opt/homebrew/bin/python3",
                "/test/skill/scripts/portal.py",
                "open",
                "--root",
                "/test/root",
            ],
        )
        self.assertEqual(data["EnvironmentVariables"]["TZ"], "Europe/Istanbul")
        self.assertNotIn("RunAtLoad", data)


if __name__ == "__main__":
    unittest.main()
