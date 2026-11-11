import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mail as digest_mail


def event(tool, arguments, result):
    return {
        "type": "item.completed",
        "item": {
            "type": "mcp_tool_call",
            "server": "codex_apps",
            "tool": tool,
            "arguments": arguments,
            "result": {"structured_content": result},
            "status": "completed",
            "error": None,
        },
    }


def reconciliation_fixture(overrides=None):
    message = {
        "id": "19a123456789abcd",
        "label_ids": ["SENT"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "subject"},
                {"name": "To", "value": digest_mail.RECIPIENT},
            ],
            "mime_type": "text/html",
            "body": {"content": "<p>full-token-abc</p>"},
        },
    }
    message.update(overrides or {})
    events = [
        event("gmail.get_profile", {}, {"email": digest_mail.RECIPIENT}),
        event(
            "gmail.search_emails", {"query": "in:sent full-token-abc"}, {"messages": []}
        ),
        event("gmail.read_email", {"message_id": message["id"]}, message),
    ]
    return "\n".join(map(json.dumps, events))


class MailTests(unittest.TestCase):
    def test_send_only_verified_self_and_exact_frozen_payload(self):
        calls = []

        def invoke(mode, payload):
            calls.append((mode, payload))
            return {
                "status": "sent",
                "account_email": digest_mail.RECIPIENT,
                "message_id": "19a123456789abcd",
                "detail": "",
            }

        result = digest_mail.deliver(
            digest_mail.RECIPIENT,
            "Reeder digest [abc123]",
            "<p>Reference: abc123</p>",
            "Reference: abc123",
            "abc123",
            invoke=invoke,
        )
        assert result == "19a123456789abcd"
        assert calls == [
            (
                "send",
                {
                    "recipient": digest_mail.RECIPIENT,
                    "subject": "Reeder digest [abc123]",
                    "html_body": "<p>Reference: abc123</p>",
                    "token": "abc123",
                },
            )
        ]

    def test_wrong_recipient_rejected_before_backend(self):
        with self.assertRaises(ValueError):
            digest_mail.deliver(
                "other@example.com",
                "s",
                "abc",
                "abc",
                "abc",
                invoke=lambda *_: self.fail("must not invoke"),
            )

    def test_missing_reference_rejected(self):
        with self.assertRaises(ValueError):
            digest_mail.deliver(
                digest_mail.RECIPIENT, "s", "<p>body</p>", "body", "abc"
            )

    def test_uncertain_or_mismatched_send_never_acknowledged_0(self):
        reply = {
            "status": "sent",
            "account_email": "other@example.com",
            "message_id": "19a123456789abcd",
        }
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.deliver(
                digest_mail.RECIPIENT, "s", "abc", "abc", "abc", invoke=lambda *_: reply
            )

    def test_uncertain_or_mismatched_send_never_acknowledged_1(self):
        reply = {
            "status": "sent",
            "account_email": digest_mail.RECIPIENT,
            "message_id": "",
        }
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.deliver(
                digest_mail.RECIPIENT, "s", "abc", "abc", "abc", invoke=lambda *_: reply
            )

    def test_uncertain_or_mismatched_send_never_acknowledged_2(self):
        reply = {
            "status": "uncertain",
            "account_email": digest_mail.RECIPIENT,
            "message_id": "",
        }
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.deliver(
                digest_mail.RECIPIENT, "s", "abc", "abc", "abc", invoke=lambda *_: reply
            )

    def test_reconcile_never_sends(self):
        modes = []

        def invoke(mode, payload):
            modes.append(mode)
            return {
                "status": "not_found",
                "account_email": digest_mail.RECIPIENT,
                "message_id": "",
                "detail": "",
            }

        assert (
            digest_mail.reconcile(
                "abc", "subject", digest_mail.RECIPIENT, invoke=invoke
            )
            is None
        )
        assert modes == ["reconcile"]

    def test_verified_reconciliation_returns_id(self):
        reply = {
            "status": "found",
            "account_email": digest_mail.RECIPIENT,
            "message_id": "19a123456789abcd",
            "detail": "",
        }
        assert (
            digest_mail.reconcile(
                "abc", "subject", digest_mail.RECIPIENT, invoke=lambda *_: reply
            )
            == "19a123456789abcd"
        )

    def test_model_command_keeps_mail_on_user_selected_astra_medium_with_scoped_approval_review(
        self,
    ):
        command = digest_mail.command_for("codex", Path("/tmp/run"))
        assert command[command.index("-m") + 1] == "gpt-6-astra"
        assert "model_reasoning_effort=medium" in command
        assert "--approve-for-me" in command
        assert command[command.index("-C") + 1] == "/tmp/run"
        assert "--ignore-user-config" in command
        assert "features.apps=true" in command
        assert "danger-full-access" not in command

    def test_prompt_confines_reconciliation_to_read_only_search(self):
        prompt = digest_mail.prompt_for(
            "reconcile",
            {"token": "abc", "subject": "s", "recipient": digest_mail.RECIPIENT},
        )
        assert "Never send" in prompt
        assert "google-workspace" in prompt
        assert "abc" in prompt

    def test_receipt_must_match_actual_gmail_tool_result(self):
        payload = {
            "recipient": digest_mail.RECIPIENT,
            "subject": "s",
            "html_body": "abc",
            "token": "abc",
        }
        reply = {
            "status": "sent",
            "account_email": digest_mail.RECIPIENT,
            "message_id": "19a123456789abcd",
        }
        profile = event("gmail.get_profile", {}, {"email": digest_mail.RECIPIENT})
        sent = event(
            "gmail.send_email",
            {
                "to": digest_mail.RECIPIENT,
                "subject": "s",
                "payload": {"mime_type": "text/html", "body": {"content": "abc"}},
            },
            {"id": "19a123456789abcd"},
        )
        logs = "\n".join(json.dumps(e) for e in [profile, sent])
        digest_mail.validate_receipt("send", payload, reply, logs)
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt(
                "send", payload, {**reply, "message_id": "madeupid1234"}, logs
            )
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt("send", payload, reply, json.dumps(profile))

    def test_duplicate_send_or_changed_payload_not_acknowledged(self):
        payload = {
            "recipient": digest_mail.RECIPIENT,
            "subject": "s",
            "html_body": "abc",
            "token": "abc",
        }
        reply = {
            "status": "sent",
            "account_email": digest_mail.RECIPIENT,
            "message_id": "19a123456789abcd",
        }
        profile = event("gmail.get_profile", {}, {"email": digest_mail.RECIPIENT})
        sent = event(
            "gmail.send_email",
            {
                "to": digest_mail.RECIPIENT,
                "subject": "s",
                "payload": {"mime_type": "text/html", "body": {"content": "CHANGED"}},
            },
            {"id": "19a123456789abcd"},
        )
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt(
                "send", payload, reply, "\n".join(map(json.dumps, [profile, sent]))
            )
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt(
                "send",
                payload,
                reply,
                "\n".join(map(json.dumps, [profile, sent, sent])),
            )

    def test_reconcile_requires_search_and_read_evidence(self):
        profile = event("gmail.get_profile", {}, {"email": digest_mail.RECIPIENT})
        search = event(
            "gmail.search_emails", {"query": "in:sent abc"}, {"messages": []}
        )
        reply = {
            "status": "not_found",
            "account_email": digest_mail.RECIPIENT,
            "message_id": "",
        }
        logs = "\n".join(map(json.dumps, [profile, search]))
        digest_mail.validate_receipt("reconcile", {"token": "abc"}, reply, logs)
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt(
                "reconcile",
                {"token": "abc"},
                {**reply, "status": "found", "message_id": "19a123456789abcd"},
                logs,
            )

    def test_reconcile_accepts_supported_search_names_with_exact_scope(self):
        profile = event("gmail.get_profile", {}, {"email": digest_mail.RECIPIENT})
        reply = {
            "status": "not_found",
            "account_email": digest_mail.RECIPIENT,
            "message_id": "",
        }
        for tool in ("gmail.search_emails", "gmail.search_email_ids"):
            for query, accepted in [
                ("in:sent full-token-abc", True),
                ("in:sent partial", False),
                ("full-token-abc", False),
            ]:
                with self.subTest(tool=tool, query=query):
                    logs = "\n".join(
                        map(
                            json.dumps,
                            [profile, event(tool, {"query": query}, {"messages": []})],
                        )
                    )
                    if accepted:
                        digest_mail.validate_receipt(
                            "reconcile", {"token": "full-token-abc"}, reply, logs
                        )
                    else:
                        with self.assertRaises(digest_mail.DeliveryError):
                            digest_mail.validate_receipt(
                                "reconcile", {"token": "full-token-abc"}, reply, logs
                            )

    def test_reconciliation_validates_full_read_evidence(self):
        digest_mail.validate_receipt(
            "reconcile",
            {
                "token": "full-token-abc",
                "subject": "subject",
                "recipient": digest_mail.RECIPIENT,
            },
            {"status": "found", "message_id": "19a123456789abcd"},
            reconciliation_fixture(),
        )

    def test_reconciliation_accepts_nullable_leaf_parts(self):
        fixture = json.loads(reconciliation_fixture().splitlines()[-1])
        message = fixture["item"]["result"]["structured_content"]
        message["payload"]["parts"] = None
        logs = reconciliation_fixture().splitlines()[:-1] + [json.dumps(fixture)]
        digest_mail.validate_receipt(
            "reconcile",
            {
                "token": "full-token-abc",
                "subject": "subject",
                "recipient": digest_mail.RECIPIENT,
            },
            {"status": "found", "message_id": "19a123456789abcd"},
            "\n".join(logs),
        )

    def test_reconciliation_rejects_mismatched_message_0(self):
        change = {"label_ids": ["INBOX"]}
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt(
                "reconcile",
                {
                    "token": "full-token-abc",
                    "subject": "subject",
                    "recipient": digest_mail.RECIPIENT,
                },
                {"status": "found", "message_id": "19a123456789abcd"},
                reconciliation_fixture(change),
            )

    def test_reconciliation_rejects_mismatched_message_1(self):
        change = {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "wrong"},
                    {"name": "To", "value": digest_mail.RECIPIENT},
                ],
                "body": {"content": "full-token-abc"},
            }
        }
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt(
                "reconcile",
                {
                    "token": "full-token-abc",
                    "subject": "subject",
                    "recipient": digest_mail.RECIPIENT,
                },
                {"status": "found", "message_id": "19a123456789abcd"},
                reconciliation_fixture(change),
            )

    def test_reconciliation_rejects_mismatched_message_2(self):
        change = {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "subject"},
                    {"name": "To", "value": "other@example.com"},
                ],
                "body": {"content": "full-token-abc"},
            }
        }
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt(
                "reconcile",
                {
                    "token": "full-token-abc",
                    "subject": "subject",
                    "recipient": digest_mail.RECIPIENT,
                },
                {"status": "found", "message_id": "19a123456789abcd"},
                reconciliation_fixture(change),
            )

    def test_reconciliation_rejects_mismatched_message_3(self):
        change = {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "subject"},
                    {"name": "To", "value": digest_mail.RECIPIENT},
                ],
                "body": {"content": "full-token-ab"},
            }
        }
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.validate_receipt(
                "reconcile",
                {
                    "token": "full-token-abc",
                    "subject": "subject",
                    "recipient": digest_mail.RECIPIENT,
                },
                {"status": "found", "message_id": "19a123456789abcd"},
                reconciliation_fixture(change),
            )

    def test_unsupported_bridge_is_deferred_without_retry(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        patcher = patch.dict(
            os.environ,
            {
                "PYTHON_FDE_MAIL_STATE_DIR": temporary.name,
                "PYTHON_FDE_CODEX_BINARY": "/missing/codex",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        calls = []

        def runner(*args):
            calls.append(args)
            raise FileNotFoundError("unavailable")

        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail._invoke("profile", {}, runner=runner)
        assert len(calls) == 1

    def test_invoke_records_profile_receipt_and_private_audit(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "PYTHON_FDE_MAIL_STATE_DIR": directory,
                "PYTHON_FDE_CODEX_BINARY": "codex",
            },
        ):

            def runner(command, prompt):
                output = Path(command[command.index("-o") + 1])
                output.write_text(
                    json.dumps(
                        {
                            "status": "verified",
                            "account_email": digest_mail.RECIPIENT,
                            "message_id": "",
                            "detail": "",
                        }
                    )
                )
                return Mock(
                    returncode=0,
                    stderr="",
                    stdout=json.dumps(
                        event("gmail.get_profile", {}, {"email": digest_mail.RECIPIENT})
                    ),
                )

            result = digest_mail._invoke("profile", {}, runner=runner)
            self.assertEqual(
                digest_mail.verify_account(invoke=lambda *_: result),
                digest_mail.RECIPIENT,
            )
            audits = list(Path(directory).rglob("request-metadata.json"))
            self.assertEqual(len(audits), 1)
            self.assertEqual(audits[0].stat().st_mode & 0o777, 0o600)

    def test_invoke_unavailable_and_invalid_output(self):
        for contents, returncode in [(None, 1), ("not json", 0), ("[]", 0)]:
            with self.subTest(
                contents=contents
            ), tempfile.TemporaryDirectory() as directory:
                with patch.dict(
                    os.environ,
                    {
                        "PYTHON_FDE_MAIL_STATE_DIR": directory,
                        "PYTHON_FDE_CODEX_BINARY": "codex",
                    },
                ):

                    def runner(command, prompt):
                        if contents is not None:
                            Path(command[command.index("-o") + 1]).write_text(contents)
                        return Mock(returncode=returncode, stderr="", stdout="")

                    with self.assertRaises(digest_mail.DeliveryError):
                        digest_mail._invoke("profile", {}, runner=runner)

    def test_process_success_and_timeout_terminate_without_retry(self):
        process = Mock(returncode=0)
        process.communicate.return_value = ("output", "")
        with patch.object(
            digest_mail.subprocess, "Popen", return_value=process
        ) as popen:
            self.assertEqual(digest_mail.run_process(["codex"], "p").stdout, "output")
            self.assertEqual(popen.call_count, 1)
        process = Mock(pid=123)
        process.communicate.side_effect = [
            digest_mail.subprocess.TimeoutExpired("codex", 1),
            ("", ""),
        ]
        with patch.object(
            digest_mail.subprocess, "Popen", return_value=process
        ) as popen:
            with patch.object(digest_mail.os, "killpg") as killpg:
                with self.assertRaises(digest_mail.DeliveryError):
                    digest_mail.run_process(["codex"], "p", timeout=1)
                self.assertEqual(popen.call_count, 1)
                self.assertEqual(
                    killpg.call_args_list[0].args, (123, digest_mail.signal.SIGTERM)
                )

    def test_timeout_kills_descendants_even_after_parent_exits(self):
        process = Mock(pid=123, returncode=-15)
        process.communicate.side_effect = [
            digest_mail.subprocess.TimeoutExpired("codex", 1),
            ("partial", ""),
        ]
        with patch.object(
            digest_mail.subprocess, "Popen", return_value=process
        ), patch.object(digest_mail.os, "killpg") as killpg:
            with self.assertRaises(digest_mail.DeliveryTimeout):
                digest_mail.run_process(["codex"], "p", timeout=1)
        self.assertEqual(
            [call.args for call in killpg.call_args_list],
            [(123, digest_mail.signal.SIGTERM), (123, digest_mail.signal.SIGKILL)],
        )

    def test_timeout_retains_partial_connector_audit(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "PYTHON_FDE_MAIL_STATE_DIR": directory,
                "PYTHON_FDE_CODEX_BINARY": "codex",
            },
        ):
            process = Mock(pid=123)
            process.communicate.side_effect = [
                digest_mail.subprocess.TimeoutExpired("codex", 1),
                ("partial events", "partial error"),
            ]
            with patch.object(
                digest_mail.subprocess, "Popen", return_value=process
            ), patch.object(digest_mail.os, "killpg"):
                with self.assertRaises(digest_mail.DeliveryError):
                    digest_mail._invoke("profile", {})
            audit = next((Path(directory) / "mail-audit").iterdir())
            self.assertEqual((audit / "events.jsonl").read_text(), "partial events")
            self.assertEqual((audit / "stderr.txt").read_text(), "partial error")
            self.assertTrue(
                json.loads((audit / "request-metadata.json").read_text())["timed_out"]
            )

    def test_malformed_events_and_text_results(self):
        self.assertEqual(digest_mail.completed_calls("invalid json"), [])
        self.assertEqual(
            digest_mail.result_data(
                {
                    "result": {
                        "content": [
                            {"type": "text", "text": "invalid"},
                            {"type": "text", "text": '{"id":"abc"}'},
                        ]
                    }
                }
            ),
            {"id": "abc"},
        )
        self.assertEqual(digest_mail.result_data({}), {})

    def test_profile_and_reconcile_fail_closed(self):
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.verify_account(
                invoke=lambda *_: {
                    "account_email": digest_mail.RECIPIENT,
                    "status": "unavailable",
                }
            )
        with self.assertRaises(digest_mail.DeliveryError):
            digest_mail.reconcile(
                "abc",
                "s",
                digest_mail.RECIPIENT,
                invoke=lambda *_: {
                    "account_email": digest_mail.RECIPIENT,
                    "status": "uncertain",
                },
            )
        with self.assertRaises(ValueError):
            digest_mail.reconcile("", "s", digest_mail.RECIPIENT)
        with self.assertRaises(ValueError):
            digest_mail.deliver(digest_mail.RECIPIENT, "s\nbad", "abc", "abc", "abc")
        with self.assertRaises(ValueError):
            digest_mail.prompt_for("invalid", {})
