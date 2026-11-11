import unittest, tempfile, json, time, sys, os
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import provider as p

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def events():
    return [
        {"type": "thread.started"},
        {
            "type": "item.completed",
            "item": {"type": "error", "message": p.DISABLED_HOST_NOTICE},
        },
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message"}},
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 10, "output_tokens": 2, "cached_input_tokens": 3},
        },
    ]


class ProviderTests(unittest.TestCase):
    def test_success_cache_routing_telemetry_error_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []

            def request(payload, timeout):
                calls.append(payload)
                return {"result": {"ok": True}, "events": events()}

            c = p.Client(d, request=request, usage_path=Path(d) / "usage.json")
            deadline = time.monotonic() + 60
            self.assertEqual(
                c.call("coach_design", {}, SCHEMA, lambda x: x, deadline), {"ok": True}
            )
            self.assertEqual(
                c.call("coach_design", {}, SCHEMA, lambda x: x, deadline), {"ok": True}
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                (calls[0]["model"], calls[0]["effort"]), ("gpt-6-astra", "medium")
            )
            self.assertEqual(c.usage["cache_hits"], 1)
            self.assertEqual(c.usage["input_tokens"], 10)
            cache = next(Path(d).glob("*.json"))
            cache.write_text("bad")
            c.call("coach_design", {}, SCHEMA, lambda x: x, deadline)

    def test_infrastructure_and_quality_failure_have_one_attempt(self):
        for error in (
            p.HostedError("hosted_auth_unavailable"),
            p.HostedError("hosted_timeout", {"input_tokens": 3, "output_tokens": 0}),
            ValueError("invalid"),
        ):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as d:
                req = Mock(side_effect=error)
                c = p.Client(d, request=req)
                with self.assertRaises(p.HostedError):
                    c.call(
                        "coach_assessment",
                        {},
                        SCHEMA,
                        lambda x: x,
                        time.monotonic() + 60,
                    )
                self.assertEqual(req.call_count, 1)
                self.assertEqual(len(c.errors), 1)

    def test_metadata_tools_and_failure_fail_closed(self):
        for ev, reason in [
            ([{"type": "turn.completed", "model": "other"}], "hosted_model_conflict"),
            (
                [{"type": "turn.completed", "reasoning_effort": "high"}],
                "hosted_effort_conflict",
            ),
            (
                [{"type": "turn.failed"}, {"type": "turn.completed"}],
                "hosted_failed_turn",
            ),
            (
                [
                    {"type": "item.completed", "item": {"type": "mcp_tool_call"}},
                    {"type": "turn.completed"},
                ],
                "hosted_tool_use_rejected",
            ),
            (
                [{"type": "new_tool"}, {"type": "turn.completed"}],
                "hosted_tool_use_rejected",
            ),
            ([], "hosted_incomplete_turn"),
        ]:
            with self.subTest(reason=reason), self.assertRaisesRegex(
                p.HostedError, reason
            ):
                p._inspect(ev, "gpt-6-astra", "medium")
        self.assertEqual(
            p._inspect(
                [
                    {
                        "type": "turn.completed",
                        "model": "gpt-6-astra",
                        "reasoning_effort": "medium",
                        "usage": {},
                    }
                ],
                "gpt-6-astra",
                "medium",
            )[1]["model"],
            "gpt-6-astra",
        )

    def test_json_events_telemetry_strict(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(ValueError):
                p._loads(text)
        with self.assertRaises(p.HostedError):
            p._parse_events("bad")
        self.assertEqual(
            p._parse_events('{"type":"thread.started"}')[0]["type"], "thread.started"
        )
        self.assertIsNone(p._completion_telemetry("bad\n{}"))
        self.assertTrue(
            p._telemetry(
                {"input_tokens": 2, "output_tokens": 1, "cached_input_tokens": 9}
            )["_telemetry_incomplete"]
        )
        self.assertTrue(
            p._telemetry(
                {
                    "input_tokens": 2,
                    "output_tokens": 1,
                    "cached_input_tokens": 0,
                    "input_cached_tokens": 1,
                }
            )["_telemetry_incomplete"]
        )

    def test_schema_shapes_limits_unions_refs(self):
        good = [
            ("x", {"type": "string", "minLength": 1, "maxLength": 2}),
            (1, {"type": "integer", "minimum": 0, "maximum": 2}),
            (
                [1],
                {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 1,
                    "maxItems": 2,
                },
            ),
            (None, {"type": ["null", "string"]}),
            (True, {"oneOf": [{"type": "boolean"}, {"type": "string"}]}),
            (1, {"anyOf": [{"type": "integer"}, {"type": "string"}]}),
            (1, {"allOf": [{"type": "integer"}]}),
            (1, {"$ref": "#/$defs/n", "$defs": {"n": {"type": "integer"}}}),
        ]
        for value, schema in good:
            p._schema(value, schema)
        bad = [
            ({}, SCHEMA),
            ({"ok": True, "extra": 1}, SCHEMA),
            ("bad", {"enum": ["a"]}),
            (2, {"const": 1}),
            ([], {"type": "array", "minItems": 1}),
            ("long", {"maxLength": 2}),
            (10, {"maximum": 2}),
            (False, {"type": "integer"}),
            (None, {"oneOf": [{"type": "string"}, {"type": "integer"}]}),
        ]
        for value, schema in bad:
            with self.assertRaises(ValueError):
                p._schema(value, schema)

    def test_auth_environment_and_deadline(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(
            os.environ, {"CODEX_HOME": d, "UNRELATED_SECRET": "redacted"}
        ):
            Path(d, "auth.json").write_text('{"auth_mode":"chatgpt"}')
            self.assertEqual(p._chatgpt_auth(), "chatgpt")
            self.assertNotIn("UNRELATED_SECRET", p._environment())
            Path(d, "auth.json").write_text("{}")
            with self.assertRaises(p.HostedError):
                p._chatgpt_auth()
        with self.assertRaises(p.HostedError):
            p._remaining(time.monotonic() - 1)

    def test_real_command_is_no_tools_and_request_errors_sanitized(self):
        with tempfile.TemporaryDirectory() as d:
            c = p.Client(d)
            command = []

            def popen(cmd, **kwargs):
                command.extend(cmd)
                Path(cmd[cmd.index("-o") + 1]).write_text('{"ok":true}')
                return Mock(
                    returncode=0,
                    communicate=Mock(
                        return_value=("\n".join(map(json.dumps, events())), "")
                    ),
                )

            with patch.object(p, "_chatgpt_auth", return_value="chatgpt"), patch.object(
                p.subprocess, "Popen", side_effect=popen
            ), patch.object(p, "_kill"):
                r = c._request(
                    {
                        "schema": SCHEMA,
                        "model": "gpt-6-astra",
                        "effort": "medium",
                        "prompt": "private",
                    },
                    30,
                )
            self.assertTrue(r["result"]["ok"])
            self.assertIn("--ignore-user-config", command)
            self.assertIn("shell_tool", command)
            self.assertNotIn("shell_zsh_fork", command)
            for process, reason in [
                (
                    Mock(returncode=1, communicate=Mock(return_value=("", ""))),
                    "hosted_cli_failed",
                ),
                (
                    Mock(
                        returncode=0,
                        communicate=Mock(
                            side_effect=p.subprocess.TimeoutExpired(
                                "codex", 1, output=""
                            )
                        ),
                    ),
                    "hosted_timeout",
                ),
            ]:
                with patch.object(p, "_chatgpt_auth"), patch.object(
                    p.subprocess, "Popen", return_value=process
                ), patch.object(p, "_kill"), self.assertRaisesRegex(
                    p.HostedError, reason
                ):
                    c._request(
                        {
                            "schema": SCHEMA,
                            "model": "gpt-6-astra",
                            "effort": "medium",
                            "prompt": "private",
                        },
                        30,
                    )

    def test_user_override_routes_every_stage_to_astra_medium(self):
        for stage in (
            "coach_design",
            "coach_assessment",
            "preflight",
            "extract",
            "format",
            "extract_luna_medium",
            "extract_sol_medium",
            "unknown",
        ):
            self.assertEqual(p.stage_route(stage), ("gpt-6-astra", "medium"))
