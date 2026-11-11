import unittest, tempfile, json, sys
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import public_refs  # noqa: F401
import coach, mail
from test_mail import event

NOW = coach.local("2026-11-03T12:00:00+03:00")
PACKET = {
    "title": "JSON boundary",
    "lesson": "A small lesson",
    "question": "Implement normalize.",
    "topic": "json",
    "kind": "ai_assisted_implementation_walkthrough",
    "resources": [],
}
ASSESS = {
    "response_type": "answer",
    "score": 2,
    "feedback": "Solid normalization; test malformed input",
    "golden_answer": "Validate shape and types at boundary",
    "misconceptions": [],
    "next_topic": "api",
    "assistance": "none",
}


class IntegrationTests(unittest.TestCase):
    def test_full_first_send_reply_assess_adapt_preview_no_send(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            with patch.object(mail, "deliver", return_value="confirmed1234") as send:
                out = coach.run(r, first=True, now=NOW)
                self.assertEqual(out["status"], "sent")
                self.assertEqual(send.call_count, 1)
                self.assertEqual(
                    coach.run(r, first=True, now=NOW)["status"], "already_started"
                )
            s = coach.load(r)
            sent = s["sent"][0]
            original = {
                "id": sent["message_id"],
                "thread_id": "thread1",
                "payload": {
                    "headers": [{"name": "Message-ID", "value": "<coach@test>"}]
                },
            }
            reply = {
                "id": "reply123",
                "thread_id": "thread1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": coach.RECIPIENT},
                        {"name": "In-Reply-To", "value": "<coach@test>"},
                    ],
                    "mime_type": "text/plain",
                    "body": {"content": "I checked input shapes using AI."},
                },
            }
            bridge = Mock()
            bridge.fetch_threads.return_value = [
                {"id": "thread1", "messages": [original, reply]}
            ]
            model = Mock()
            model.call.return_value = {**ASSESS, "assistance": "ai_assisted"}
            with patch.object(coach, "client", return_value=model):
                s = coach.poll(r, s, NOW, bridge)
                self.assertEqual(len(s["assessments"]), 1)
                self.assertEqual(s["assessments"][0]["assistance"], "ai_assisted")
                s = coach.poll(r, s, NOW, bridge)
                self.assertEqual(len(s["assessments"]), 1)
            with patch.object(coach, "client", return_value=model):
                model.call.side_effect = (
                    lambda stage, data, schema, validate, *a, **k: validate(PACKET)
                )
                self.assertEqual(coach.generate(r, s)["topic"], "json")
            coach.save(r, s)
            with patch.object(coach, "due", return_value="slot"), patch.object(
                coach, "generate", return_value=PACKET
            ), patch.object(mail, "deliver") as send:
                s["last_reply_check"] = NOW.isoformat()
                coach.save(r, s)
                result = coach.run(r, preview=True, now=NOW)
                self.assertEqual(result["status"], "preview")
                send.assert_not_called()
                self.assertIsNone(coach.load(r)["pending"])

    def test_quoted_html_and_mime_alternatives_never_become_authored_answer(self):
        part = {
            "mime_type": "text/html",
            "body": {
                "content": '<div>My actual answer</div><div class="gmail_quote"><div>Golden answer 3/3</div></div>'
            },
        }
        self.assertIn("My actual answer", coach.body_text(part))
        self.assertNotIn("Golden", coach.body_text(part))
        part = {
            "mime_type": "multipart/alternative",
            "parts": [
                {"mime_type": "text/plain", "body": {"content": "Authored plain"}},
                {
                    "mime_type": "text/html",
                    "body": {"content": "<p>Different HTML quoted solution</p>"},
                },
            ],
        }
        self.assertEqual(coach.body_text(part), "Authored plain")
        part = {
            "mime_type": "text/html",
            "body": {"content": "<blockquote>Only quoted answer</blockquote>"},
        }
        self.assertFalse(coach.body_text(part).strip())

    def test_future_pending_and_daily_cap_pause_gates(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            s = coach.plan(coach.initial(), NOW)
            s = coach.prepare(r, s, PACKET, "2026-11-03T20:00:00+03:00")
            with patch.object(mail, "deliver") as send:
                self.assertEqual(coach.run(r, now=NOW)["status"], "pending_not_due")
                send.assert_not_called()
            s = {
                **s,
                "frequency": [1, 1],
                "pending": None,
                "sent": [{"sent_at": NOW.isoformat()}],
            }
            self.assertIsNone(coach.due(s, NOW))

    def test_controls_poll_and_ungraded_nonquestion_reply(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            s = coach.initial()
            sent = {
                "message_id": "outgoing123",
                "sent_at": NOW.isoformat(),
                "token": "token",
                "packet": PACKET,
                "answered": False,
            }
            s["sent"] = [sent]
            original = {
                "id": "outgoing123",
                "thread_id": "t",
                "payload": {"headers": [{"name": "Message-ID", "value": "<id>"}]},
            }

            def reply(text, id="reply123"):
                return {
                    "id": id,
                    "thread_id": "t",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": coach.RECIPIENT},
                            {"name": "In-Reply-To", "value": "<id>"},
                        ],
                        "body": {"content": text},
                    },
                }

            bridge = Mock()
            bridge.fetch_threads.return_value = [
                {"messages": [original, reply("PAUSE")]}
            ]
            s = coach.poll(r, s, NOW, bridge)
            self.assertTrue(s["paused"])
            self.assertFalse(s["assessments"])
            self.assertEqual(coach.control(s, "FREQUENCY 1")["frequency"], [1, 1])
            self.assertTrue(coach.control(s, "SKIP")["sent"][0]["skipped"])
            self.assertEqual(
                coach.poll(r, coach.initial(), NOW, bridge), coach.initial()
            )

    def test_mail_scoped_threads_validate_actual_transcript_and_forbidden_attempts(
        self,
    ):
        profile = event("gmail.get_profile", {}, {"email": mail.RECIPIENT})
        root = {"id": "outgoing123", "payload": {}}
        read = event(
            "gmail.read_email_thread",
            {"message_id": "outgoing123"},
            {"id": "thread1", "messages": [root]},
        )
        events = "\n".join(map(json.dumps, [profile, read]))
        reply = {"status": "verified", "account_email": mail.RECIPIENT}

        def invoke(*a, **k):
            return reply, events

        self.assertEqual(
            mail.fetch_threads(["outgoing123"], invoke)[0]["id"], "thread1"
        )
        for mode, payload, tool in [
            ("profile", {}, "gmail.delete_email"),
            ("replies", {"message_ids": ["outgoing123"]}, "gmail.send_email"),
            ("reconcile", {"token": "a"}, "gmail.create_draft"),
        ]:
            bad = event(tool, {}, {})
            bad["item"]["status"] = "failed"
            bad["item"]["error"] = {"message": "rejected"}
            with self.assertRaises(mail.DeliveryError):
                mail.validate_receipt(mode, payload, reply, json.dumps(bad))
        duplicate = event("gmail.send_email", {}, {})
        events = "\n".join(map(json.dumps, [duplicate, duplicate]))
        with self.assertRaises(mail.DeliveryError):
            mail.validate_attempts("send", {}, events)
        with self.assertRaises(ValueError):
            mail.fetch_threads([])

    def test_generate_rejects_unverified_url_or_second_pending_question(self):
        with tempfile.TemporaryDirectory() as d:
            m = Mock()
            m.call.side_effect = (
                lambda stage, data, schema, validate, *a, **k: validate(
                    {
                        **PACKET,
                        "resources": [
                            {"title": "bad", "url": "https://unverified.example"}
                        ],
                    }
                )
            )
            with patch.object(coach, "client", return_value=m), self.assertRaises(
                ValueError
            ):
                coach.generate(d, coach.initial())
            s = coach.initial()
            s["sent"] = [{"packet": PACKET, "answered": False}]
            m.call.side_effect = (
                lambda stage, data, schema, validate, *a, **k: validate(PACKET)
            )
            with patch.object(coach, "client", return_value=m), self.assertRaises(
                ValueError
            ):
                coach.generate(d, s)

    def test_cli_status_and_controls(self):
        with tempfile.TemporaryDirectory() as d:
            for command in ("pause", "resume", "set-frequency", "status"):
                with patch.object(
                    sys, "argv", ["coach.py", command, "--root", d]
                ), patch("builtins.print"):
                    coach.main()
            self.assertEqual(coach.load(d)["frequency"], [1, 3])

    def test_preview_existing_pending_cannot_send_or_reconcile(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            state = coach.prepare(r, coach.initial(), PACKET, NOW.isoformat())
            for attempted in (None, NOW.isoformat()):
                state = {
                    **state,
                    "pending": {**state["pending"], "attempted_at": attempted},
                }
                coach.save(r, state)
                with patch.object(mail, "deliver") as send, patch.object(
                    mail, "reconcile"
                ) as reconcile:
                    self.assertEqual(
                        coach.run(r, preview=True, now=NOW)["status"], "preview"
                    )
                    send.assert_not_called()
                    reconcile.assert_not_called()
                    self.assertIsNotNone(coach.load(r)["pending"])

    def test_crashed_unattempted_expired_pending_does_not_stall_next_day(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            coach.prepare(r, coach.initial(), PACKET, "2026-11-02T10:00:00+03:00")
            with patch.object(coach, "due", return_value=None), patch.object(
                mail, "deliver"
            ) as send:
                self.assertEqual(coach.run(r, now=NOW)["status"], "not_due")
                send.assert_not_called()
            self.assertIsNone(coach.load(r)["pending"])
            self.assertEqual(len(list((r / "messages").glob("*/cancelled.json"))), 1)

    def test_clarification_is_unscored_pending_and_assistance_never_downgrades(self):
        with tempfile.TemporaryDirectory() as d:
            state = coach.initial()
            sent = {
                "token": "tok",
                "packet": {**PACKET, "kind": "unaided_concept_check"},
                "answered": False,
                "assistance": "hint",
            }
            state["sent"] = [sent]
            model = Mock()
            model.call.return_value = {
                **ASSESS,
                "response_type": "clarification",
                "score": None,
                "assistance": "none",
            }
            with patch.object(coach, "client", return_value=model):
                state = coach.assess(
                    d, state, {"id": "reply"}, sent, "What do you mean by malformed?"
                )
            self.assertFalse(state["sent"][0]["answered"])
            self.assertIsNone(state["assessments"][0]["score"])
            self.assertEqual(state["assessments"][0]["assistance"], "hint")
            self.assertEqual(state["topics"]["json"]["status"], "not_assessed")
            with self.assertRaises(ValueError):
                coach.validate_assessment({**ASSESS, "response_type": "clarification"})
