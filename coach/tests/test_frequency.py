import copy, json, random, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import coach, mail

NOW = coach.local("2026-11-03T08:40:00+03:00")


class FrequencyTests(unittest.TestCase):
    def test_six_daily_slots_are_always_feasible_spaced_and_random(self):
        schedules = set()
        for seed in range(150):
            state = coach.plan(
                {**coach.initial(), "frequency": [6, 6]}, NOW, random.Random(seed)
            )
            times = [coach.local(slot["at"]) for slot in state["plan"]["slots"]]
            self.assertEqual(len(times), 6)
            self.assertTrue(all(9 <= time.hour < 21 for time in times))
            self.assertTrue(
                all(time.hour * 60 + time.minute < 21 * 60 - 15 for time in times)
            )
            self.assertTrue(
                all(
                    (later - earlier).total_seconds() >= 5400
                    for earlier, later in zip(times, times[1:])
                )
            )
            schedules.add(tuple(time.isoformat() for time in times))
        self.assertGreater(len(schedules), 140)

    def test_increase_today_preserves_evidence_and_replans_only_future_slots(self):
        sent = {"sent_at": "2026-11-03T08:22:00+03:00", "message_id": "sent-one"}
        state = {
            **coach.initial(),
            "frequency": [1, 3],
            "sent": [sent],
            "last_sent_at": sent["sent_at"],
            "plan": {
                "day": "2026-11-03",
                "slots": [
                    {"at": "2026-11-03T09:18:00+03:00", "status": "sent"},
                    {"at": "2026-11-03T16:13:00+03:00", "status": "planned"},
                ],
            },
            "processed_replies": ["reply-one"],
            "topics": {"json": {"status": "practiced"}},
        }
        original = copy.deepcopy(state)
        updated = coach.set_frequency(state, 6, 6, NOW, random.Random(8))
        self.assertEqual(state, original)
        self.assertEqual(updated["frequency"], [6, 6])
        self.assertEqual(updated["sent"], state["sent"])
        self.assertEqual(updated["processed_replies"], state["processed_replies"])
        self.assertEqual(updated["topics"], state["topics"])
        self.assertEqual(updated["plan"]["slots"][0], state["plan"]["slots"][0])
        planned = [
            coach.local(slot["at"])
            for slot in updated["plan"]["slots"]
            if slot["status"] == "planned"
        ]
        self.assertEqual(len(planned), 5)
        self.assertTrue(all(time > NOW for time in planned))
        times = [coach.local(slot["at"]) for slot in updated["plan"]["slots"]]
        self.assertTrue(
            all(
                (later - earlier).total_seconds() >= 5400
                for earlier, later in zip(times, times[1:])
            )
        )
        self.assertEqual(coach.plan(updated, NOW, random.Random(99)), updated)

    def test_same_frequency_is_idempotent_and_pending_plan_is_preserved(self):
        state = coach.plan(
            {**coach.initial(), "frequency": [4, 4]}, NOW, random.Random(1)
        )
        self.assertEqual(
            coach.set_frequency(state, 4, 4, NOW, random.Random(99)), state
        )
        for attempted in (None, NOW.isoformat()):
            pending = {
                "token": "frozen",
                "attempted_at": attempted,
                "slot": state["plan"]["slots"][0]["at"],
            }
            held = {**state, "pending": pending}
            updated = coach.set_frequency(held, 6, 6, NOW)
            self.assertEqual(updated["pending"], pending)
            self.assertEqual(updated["plan"], held["plan"])
            self.assertEqual(updated["frequency"], [6, 6])

    def test_late_increase_never_catches_up_and_reduction_respects_delivered_cap(self):
        now = coach.local("2026-11-03T20:45:00+03:00")
        state = {
            **coach.initial(),
            "frequency": [1, 3],
            "plan": {
                "day": "2026-11-03",
                "slots": [{"at": "2026-11-03T10:00:00+03:00", "status": "missed"}],
            },
        }
        updated = coach.set_frequency(state, 4, 4, now, random.Random(1))
        self.assertEqual(updated["plan"]["slots"], state["plan"]["slots"])
        self.assertIsNone(coach.due(updated, now))
        early = coach.local("2026-11-03T12:00:00+03:00")
        state = {
            **coach.initial(),
            "frequency": [4, 4],
            "sent": [
                {"sent_at": "2026-11-03T09:00:00+03:00"},
                {"sent_at": "2026-11-03T11:00:00+03:00"},
            ],
            "plan": {"day": "2026-11-03", "slots": []},
        }
        reduced = coach.set_frequency(state, 1, 1, early)
        self.assertFalse(reduced["plan"]["slots"])
        self.assertIsNone(coach.due(reduced, early))

    def test_frequency_controls_keep_maximum_semantics_and_invalid_input_is_ignored(
        self,
    ):
        state = {**coach.initial(), "frequency": [4, 4]}
        self.assertEqual(coach.control(state, "FREQUENCY 6")["frequency"], [4, 6])
        self.assertEqual(coach.control(state, "FREQUENCY 2")["frequency"], [2, 2])
        for text in ("FREQUENCY 0", "FREQUENCY 7", "FREQUENCY 4 please"):
            self.assertEqual(coach.control(state, text), state)

    def test_cli_sets_explicit_minimum_preserves_legacy_maximum_and_rejects_invalid_range(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:

            def command(*options):
                with patch.object(
                    sys,
                    "argv",
                    ["coach.py", "set-frequency", "--root", directory, *options],
                ), patch("builtins.print"):
                    coach.main()

            command("--min", "4", "--max", "4")
            self.assertEqual(coach.load(directory)["frequency"], [4, 4])
            command("--max", "6")
            self.assertEqual(coach.load(directory)["frequency"], [1, 6])
            before = coach.load(directory)
            with self.assertRaises(SystemExit):
                command("--min", "6", "--max", "4")
            self.assertEqual(coach.load(directory), before)

    def test_reply_frequency_six_is_control_without_model_assessment(self):
        with tempfile.TemporaryDirectory() as directory:
            sent = {
                "message_id": "original",
                "sent_at": NOW.isoformat(),
                "packet": {"question": "Why?"},
                "answered": False,
            }
            state = {**coach.initial(), "sent": [sent]}
            original = {
                "id": "original",
                "thread_id": "thread",
                "payload": {"headers": [{"name": "Message-ID", "value": "<original>"}]},
            }
            reply = {
                "id": "reply",
                "thread_id": "thread",
                "payload": {
                    "headers": [
                        {"name": "From", "value": coach.RECIPIENT},
                        {"name": "In-Reply-To", "value": "<original>"},
                    ],
                    "body": {"content": "FREQUENCY 6"},
                },
            }

            class Bridge:
                @staticmethod
                def fetch_threads(ids):
                    return [{"messages": [original, reply]}]

            with patch.object(
                coach,
                "assess",
                side_effect=AssertionError("control must not be graded"),
            ):
                updated = coach.poll(directory, state, NOW, Bridge)
            self.assertEqual(updated["frequency"], [state["frequency"][0], 6])
            self.assertEqual(updated["processed_replies"], ["reply"])


if __name__ == "__main__":
    unittest.main()
