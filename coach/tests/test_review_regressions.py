import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import coach, mail

PACKET = {
    "title": "Python",
    "lesson": "Comparisons",
    "question": "Compare values",
    "topic": "python",
    "kind": "question",
    "resources": [],
}


class ReviewRegressionTests(unittest.TestCase):
    def test_plain_python_comparison_and_markup_code_are_preserved(self):
        sent = {
            "message_id": "original",
            "thread_id": "thread",
            "rfc_id": "<coach@example.test>",
        }
        for code in ["return a < b and c > d", 'template = "<div>hello</div>"']:
            message = {
                "id": "reply",
                "thread_id": "thread",
                "payload": {
                    "headers": [
                        {"name": "From", "value": coach.RECIPIENT},
                        {"name": "In-Reply-To", "value": sent["rfc_id"]},
                    ],
                    "mime_type": "text/plain",
                    "body": {"content": code},
                },
            }
            self.assertEqual(coach.reply_text(message, sent), code)

    def test_generation_cannot_cross_hours_or_slot_window(self):
        for start, end, slot in [
            (
                "2026-11-05T20:59:00+03:00",
                "2026-11-05T21:01:00+03:00",
                "2026-11-05T20:30:00+03:00",
            ),
            (
                "2026-11-05T09:44:00+03:00",
                "2026-11-05T09:46:00+03:00",
                "2026-11-05T09:00:00+03:00",
            ),
        ]:
            with self.subTest(start=start), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                real_local = coach.local
                current = [real_local(start)]
                state = {
                    **coach.initial(),
                    "plan": {
                        "day": "2026-11-05",
                        "slots": [{"at": slot, "status": "planned"}],
                    },
                }
                coach.save(root, state)

                def generate(*args):
                    current[0] = real_local(end)
                    return PACKET

                with patch.object(
                    coach,
                    "local",
                    side_effect=lambda value=None: real_local(value)
                    if value
                    else current[0],
                ), patch.object(coach, "generate", side_effect=generate), patch.object(
                    mail, "deliver", return_value="confirmed1234"
                ) as deliver:
                    result = coach.run(root)
                self.assertEqual(result["status"], "generation_slot_expired")
                deliver.assert_not_called()
                self.assertIsNone(coach.load(root)["pending"])
