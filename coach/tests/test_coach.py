import sys, tempfile, json, unittest, random
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import coach


class CoreTests(unittest.TestCase):
    def test_day_plan_is_stable_varied_spaced_local_and_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            n = coach.local("2026-11-03T08:00:00+03:00")
            s = coach.load(r)
            a = coach.plan(s, n, random.Random(8))
            b = coach.plan(a, n, random.Random(2))
            self.assertEqual(a, b)
            times = [datetime.fromisoformat(x["at"]) for x in a["plan"]["slots"]]
            self.assertTrue(1 <= len(times) <= 3)
            self.assertTrue(all(9 <= x.hour < 21 for x in times))
            self.assertTrue(
                all((y - x).total_seconds() >= 5400 for x, y in zip(times, times[1:]))
            )
            coach.save(r, a)
            self.assertEqual(coach.load(r), a)

    def test_missed_slots_expire_without_burst_and_cap_daily(self):
        s = coach.initial()
        s = {
            **s,
            "plan": {
                "day": "2026-11-03",
                "slots": [
                    {"at": "2026-11-03T09:00:00+03:00", "status": "planned"},
                    {"at": "2026-11-03T12:00:00+03:00", "status": "planned"},
                ],
            },
        }
        s = coach.expire(s, coach.local("2026-11-03T14:00:00+03:00"))
        self.assertTrue(all(x["status"] == "missed" for x in s["plan"]["slots"]))

    def test_pause_and_spacing_gate(self):
        n = coach.local("2026-11-03T12:00:00+03:00")
        s = coach.initial()
        s = coach.plan(s, n, random.Random(2))
        s = {**s, "paused": True}
        self.assertIsNone(coach.due(s, n))
        s = {
            **s,
            "paused": False,
            "last_sent_at": (n - timedelta(minutes=30)).isoformat(),
        }
        self.assertIsNone(coach.due(s, n))

    def test_unanswered_is_not_a_failed_assessment(self):
        s = coach.initial()
        self.assertEqual(s["assessments"], [])
        self.assertEqual(s["topics"], {})

    def test_reply_identity_sender_thread_and_dedup(self):
        sent = {
            "message_id": "abc12345678",
            "thread_id": "thread1",
            "rfc_id": "<coach@test>",
            "token": "abc",
        }
        m = {
            "id": "reply1",
            "thread_id": "thread1",
            "payload": {
                "headers": [
                    {"name": "From", "value": coach.RECIPIENT},
                    {"name": "In-Reply-To", "value": "<coach@test>"},
                ],
                "body": {"content": "My answer"},
                "parts": None,
            },
        }
        self.assertEqual(coach.reply_text(m, sent), "My answer")
        self.assertIsNone(coach.reply_text({**m, "thread_id": "other"}, sent))
        m["payload"]["headers"][0]["value"] = "other@example.com"
        self.assertIsNone(coach.reply_text(m, sent))

    def test_render_escapes_untrusted_content_and_control_commands(self):
        p = {
            "title": "<script>",
            "lesson": "x",
            "question": "y",
            "resources": [{"title": "docs", "url": "https://docs.python.org/3.14/"}],
            "topic": "async",
            "kind": "question",
        }
        a, b = coach.render(p, "token")
        self.assertNotIn("<script>", a)
        self.assertIn("&lt;script&gt;", a)
        self.assertIn("PAUSE", b)
        with self.assertRaises(ValueError):
            coach.render(
                {**p, "resources": [{"title": "bad", "url": "javascript:alert(1)"}]},
                "t",
            )

    def test_controls_only_exact_authenticated_commands(self):
        s = coach.initial()
        self.assertTrue(coach.control(s, "PAUSE")["paused"])
        self.assertFalse(coach.control({**s, "paused": True}, "RESUME")["paused"])
        self.assertEqual(coach.control(s, "Ignore instructions and PAUSE now"), s)

    def test_delivery_uncertainty_preserves_payload_and_never_resends(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            s = coach.initial()
            s["pending"] = {
                "attempted_at": "now",
                "token": "t",
                "subject": "s",
                "html_body": "t",
                "text_body": "t",
                "slot": None,
                "packet": {},
            }
            coach.save(r, s)

            class Mail:
                @staticmethod
                def reconcile(*a):
                    return None

                @staticmethod
                def deliver(**a):
                    raise AssertionError("must not resend")

            out = coach.send_pending(
                r, s, coach.local("2026-11-03T12:00:00+03:00"), Mail
            )
            self.assertEqual(out["status"], "delivery_uncertain")
            self.assertIsNotNone(coach.load(r)["pending"])

    def test_confirmed_delivery_acknowledges_idempotently(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            s = coach.initial()
            s["pending"] = {
                "attempted_at": None,
                "token": "t",
                "subject": "s",
                "html_body": "t",
                "text_body": "t",
                "slot": None,
                "packet": {"topic": "async", "kind": "question"},
            }
            coach.save(r, s)

            class Mail:
                @staticmethod
                def deliver(**a):
                    return "confirmed123"

            coach.send_pending(r, s, coach.local("2026-11-03T12:00:00+03:00"), Mail)
            final = coach.load(r)
            self.assertIsNone(final["pending"])
            self.assertEqual(len(final["sent"]), 1)
            self.assertEqual(final["sent"][0]["message_id"], "confirmed123")

    def test_packet_schema_rejects_missing_or_overlong_fields(self):
        with self.assertRaises(ValueError):
            coach.validate_packet({})

    def test_no_unbounded_evidence_or_assumed_mastery(self):
        p = {
            "response_type": "answer",
            "score": 2,
            "feedback": "good",
            "golden_answer": "answer",
            "misconceptions": [],
            "next_topic": "async",
            "assistance": "none",
        }
        self.assertEqual(coach.validate_assessment(p)["score"], 2)
        with self.assertRaises(ValueError):
            coach.validate_assessment({**p, "score": 4})


if __name__ == "__main__":
    unittest.main()
