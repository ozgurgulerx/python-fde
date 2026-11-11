import json
import re
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import portal


def message(title="Lesson one", body="print(1)", **extra):
    return {
        "packet": {"title": title, "topic": "Python", "kind": "lesson"},
        "text_body": body,
        "sent_at": "2026-11-11T10:00:00+03:00",
        **extra,
    }


class PortalTests(unittest.TestCase):
    def state(self, root, data, name="state.json"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def test_archive_current_and_pending_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.state(root, {"sent": [message()], "pending": message("Queued")})
            self.state(
                root, {"sent": [message("Old lesson")]}, "history/old/state.json"
            )
            path = portal.build(root)
            text = path.read_text()
            self.assertIn("Lesson one", text)
            self.assertIn("Old lesson", text)
            self.assertIn("Queued", text)
            self.assertIn("Not confirmed delivered", text)
            self.assertIn("2</strong><span>Delivered emails", text)
            self.assertIn('data-course="current"', text)
            self.assertIn('data-course="archive"', text)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_untrusted_content_is_escaped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.state(
                root,
                {
                    "sent": [
                        message("<script>bad()</script>", "<img src=x onerror=bad()>")
                    ],
                    "pending": None,
                },
            )
            text = portal.build(root).read_text()
            self.assertNotIn("<script>bad()", text)
            self.assertNotIn("<img src=x", text)
            self.assertIn("&lt;script&gt;bad()", text)
            self.assertIn("&lt;img src=x onerror=bad()&gt;", text)

    def test_empty_missing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            text = portal.build(Path(directory)).read_text()
            self.assertIn("Your fresh start", text)
            self.assertIn("0</strong><span>Delivered emails", text)

    def test_open_explicitly_uses_safari(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            portal.subprocess, "run"
        ) as run:
            portal.main(["open", "--root", directory])
            run.assert_called_once_with(
                [
                    "/usr/bin/open",
                    "-a",
                    "Safari",
                    str(Path(directory) / "portal/index.html"),
                ],
                check=True,
            )

    def test_invalid_state_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state.json").write_text("not json")
            with self.assertRaises(json.JSONDecodeError):
                portal.build(root)

    def test_permalinks_survive_newer_mail_and_hostile_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = message("Original", token='unsafe"/><script>bad()</script>')
            self.state(root, {"sent": [old], "pending": None})
            first = portal.build(root).read_text()
            original_id = re.search(r'<details id="([^"]+)"', first).group(1)
            newer = message("Newer", token="new", sent_at="2026-11-12T10:00:00+03:00")
            self.state(root, {"sent": [old, newer], "pending": None})
            second = portal.build(root).read_text()
            original_details = (
                second.split("<h2>Original</h2>")[0]
                .rsplit('<details id="', 1)[1]
                .split('"', 1)[0]
            )
            self.assertEqual(original_id, original_details)
            self.assertRegex(original_id, r"^lesson-[a-f0-9]{24}$")
            self.assertIn('href="#' + original_id + '"', second)
