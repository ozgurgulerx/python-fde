import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import public_refs  # noqa: F401
import coach
import memory

START = datetime(2026, 11, 11, 10, 0, tzinfo=memory.TZ)


def sent(token, topic, at, kind="unaided_concept_check", question="Q?", answered=False):
    return {
        "token": token,
        "sent_at": at.isoformat(),
        "answered": answered,
        "packet": {"topic": topic, "kind": kind, "question": question, "title": topic},
    }


def assessed(token, at, score, assistance="none", misconceptions=(), kind="answer"):
    return {
        "question_token": token,
        "at": at.isoformat(),
        "score": score,
        "assistance": assistance,
        "response_type": kind,
        "misconceptions": list(misconceptions),
    }


def course(*pairs):
    """Build a state from (token, topic, day_offset, score, assistance, misconceptions)."""
    state = {"sent": [], "assessments": []}
    for token, topic, offset, score, assistance, wrong in pairs:
        at = START + timedelta(days=offset)
        state["sent"].append(sent(token, topic, at, answered=score is not None))
        if score is not None:
            state["assessments"].append(assessed(token, at, score, assistance, wrong))
    return state


class TopicHistoryTests(unittest.TestCase):
    def test_every_attempt_is_kept_not_only_the_latest(self):
        state = course(
            ("a" * 32, "names", 0, 1, "none", ()), ("b" * 32, "names", 1, 3, "none", ())
        )
        record = memory.build(state)["topics"]["names"]
        self.assertEqual([h["score"] for h in record["history"]], [1, 3])
        self.assertEqual(
            (record["latest_score"], record["best_score"], record["attempts"]),
            (3, 3, 2),
        )

    def test_unaided_passes_climb_the_review_ladder(self):
        pairs = [
            (str(i) * 32, "loops", offset, 2, "none", ())
            for i, offset in enumerate((0, 1, 4, 11, 32))
        ]
        intervals = [
            memory.build(course(*pairs[:n]))["topics"]["loops"]["interval_days"]
            for n in range(1, 6)
        ]
        self.assertEqual(intervals, [1, 3, 7, 21, 21])

    def test_a_failed_or_assisted_attempt_resets_the_ladder(self):
        state = course(
            ("a" * 32, "loops", 0, 3, "none", ()),
            ("b" * 32, "loops", 1, 3, "none", ()),
            ("c" * 32, "loops", 4, 3, "ai_assisted", ()),
        )
        record = memory.build(state)["topics"]["loops"]
        self.assertEqual(record["interval_days"], 1)
        self.assertEqual(record["unaided_passes"], 2)
        self.assertEqual(
            memory.build(course(("a" * 32, "loops", 0, 1, "none", ())))["topics"][
                "loops"
            ]["interval_days"],
            1,
        )

    def test_status_needs_two_unaided_passes_and_a_delayed_one_for_retained(self):
        one = course(("a" * 32, "t", 0, 3, "none", ()))
        two = course(
            ("a" * 32, "t", 0, 3, "none", ()), ("b" * 32, "t", 1, 2, "none", ())
        )
        spaced = course(
            ("a" * 32, "t", 0, 3, "none", ()), ("b" * 32, "t", 8, 2, "none", ())
        )
        helped = course(
            ("a" * 32, "t", 0, 3, "hint", ()),
            ("b" * 32, "t", 8, 3, "solution_seen", ()),
        )
        statuses = [
            memory.build(s)["topics"]["t"]["status"] for s in (one, two, spaced, helped)
        ]
        self.assertEqual(
            statuses, ["practiced", "independent", "retained", "practiced"]
        )

    def test_unscored_replies_and_unanswered_lessons_are_not_attempts(self):
        state = course(("a" * 32, "names", 0, None, "none", ()))
        state["assessments"].append(
            assessed("a" * 32, START, None, kind="clarification")
        )
        state["assessments"].append(assessed("z" * 32, START, 3))
        profile = memory.build(state)
        self.assertEqual(profile["topics"], {})
        self.assertEqual(profile["introduced"], ["names"])
        self.assertEqual(profile["totals"]["scored_attempts"], 0)


class MisconceptionTests(unittest.TestCase):
    def test_repeats_are_counted_across_wording_and_topics(self):
        state = course(
            ("a" * 32, "names", 0, 1, "none", ("Thinks = compares values",)),
            ("b" * 32, "mutation", 1, 1, "none", ("thinks  =  compares values.",)),
        )
        ledger = memory.build(state)["misconceptions"]
        self.assertEqual(len(ledger), 1)
        self.assertEqual((ledger[0]["count"], ledger[0]["status"]), (2, "open"))
        self.assertEqual(ledger[0]["topics"], ["names", "mutation"])

    def test_cleared_only_after_two_later_unaided_passes(self):
        base = [("a" * 32, "names", 0, 1, "none", ("alias is a copy",))]
        once = course(*base, ("b" * 32, "names", 1, 3, "none", ()))
        twice = course(
            *base,
            ("b" * 32, "names", 1, 3, "none", ()),
            ("c" * 32, "names", 4, 2, "none", ()),
        )
        helped = course(
            *base,
            ("b" * 32, "names", 1, 3, "hint", ()),
            ("c" * 32, "names", 4, 3, "hint", ()),
        )
        statuses = [
            memory.build(s)["misconceptions"][0]["status"]
            for s in (once, twice, helped)
        ]
        self.assertEqual(statuses, ["open", "cleared", "open"])


class EngagementTests(unittest.TestCase):
    def test_reply_rate_hours_and_trailing_unanswered_streak(self):
        state = course(
            ("a" * 32, "names", 0, 2, "none", ()),
            ("b" * 32, "loops", 1, None, "none", ()),
            ("c" * 32, "dicts", 2, None, "none", ()),
        )
        state["sent"].append(
            sent("d" * 32, "reading", START, kind="reading", question="")
        )
        result = memory.build(state)["engagement"]
        self.assertEqual(
            result["by_kind"]["unaided_concept_check"],
            {"sent": 3, "asked": 3, "answered": 1, "reply_rate": 0.33},
        )
        self.assertIsNone(result["by_kind"]["reading"]["reply_rate"])
        self.assertEqual(result["by_hour"], {"10": {"asked": 3, "answered": 1}})
        self.assertEqual(result["unanswered_streak"], 2)


class DayLedgerTests(unittest.TestCase):
    DAY = {
        "day": 1,
        "title": "A support ticket, by hand",
        "topics": ["names", "strings"],
        "status": "reviewed",
        "completed": "2026-11-12",
        "score": 2,
        "assistance": "none",
        "misconceptions": ["alias is a copy"],
    }

    def test_reviewed_days_count_as_attempts_on_each_topic(self):
        profile = memory.build(
            {"sent": [], "assessments": []},
            [self.DAY, {**self.DAY, "day": 2, "status": "assigned", "score": None}],
        )
        self.assertEqual(sorted(profile["topics"]), ["names", "strings"])
        self.assertEqual(profile["topics"]["names"]["history"][0]["ref"], "day01")
        self.assertEqual(
            (profile["totals"]["days_assigned"], profile["totals"]["days_reviewed"]),
            (2, 1),
        )
        self.assertEqual(profile["misconceptions"][0]["count"], 2)

    def test_ledger_is_read_from_the_repository_and_bad_files_are_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.assertEqual(memory.load_days(repo), [])
            (repo / "memory").mkdir()
            (repo / "memory/days.json").write_text("{not json")
            self.assertEqual(memory.load_days(repo), [])
            (repo / "memory/days.json").write_text(json.dumps({"day": 1}))
            self.assertEqual(memory.load_days(repo), [])
            (repo / "memory/days.json").write_text(json.dumps([self.DAY, "junk"]))
            self.assertEqual(memory.load_days(repo), [self.DAY])


class GeneratorViewTests(unittest.TestCase):
    def test_view_is_compact_and_lists_only_due_reviews_and_open_misconceptions(self):
        state = course(
            ("a" * 32, "names", 0, 2, "none", ("alias is a copy",)),
            ("b" * 32, "loops", 3, 2, "none", ()),
        )
        with tempfile.TemporaryDirectory() as directory:
            view = memory.for_generator(state, START + timedelta(days=2), directory)
        self.assertEqual([r["topic"] for r in view["reviews_due"]], ["names"])
        self.assertEqual(view["open_misconceptions"][0]["text"], "alias is a copy")
        self.assertNotIn("history", view["topics"][0])
        self.assertIn("never state or imply mastery", view["policy"])
        self.assertEqual(view["recent_days"], [])

    def test_profile_is_deterministic_and_json_serialisable(self):
        state = course(("a" * 32, "names", 0, 2, "none", ("alias is a copy",)))
        self.assertEqual(
            json.dumps(memory.build(state), sort_keys=True),
            json.dumps(memory.build(state), sort_keys=True),
        )
        self.assertEqual(memory.build({})["course_started"], None)


class CoachHookTests(unittest.TestCase):
    PACKET = {
        "title": "T",
        "lesson": "L",
        "question": "",
        "topic": "names",
        "kind": "reading",
        "resources": [],
    }

    def generate(self, root, state):
        model = Mock()
        model.call.side_effect = (
            lambda stage, data, schema, validate, *a, **k: validate(self.PACKET)
        )
        with patch.object(coach, "client", return_value=model):
            packet = coach.generate(root, state)
        return packet, model.call.call_args.args[1]

    def test_generator_receives_the_memory_view(self):
        state = {**coach.initial(), **course(("a" * 32, "loops", 0, 2, "none", ()))}
        with tempfile.TemporaryDirectory() as directory:
            packet, data = self.generate(Path(directory), state)
        self.assertEqual(packet["topic"], "names")
        self.assertEqual(data["learner_memory"]["topics"][0]["topic"], "loops")

    def test_a_memory_fault_never_blocks_generation(self):
        state = {**coach.initial(), **course(("a" * 32, "loops", 0, 2, "none", ()))}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            memory, "for_generator", side_effect=ValueError("broken")
        ):
            packet, data = self.generate(Path(directory), state)
            self.assertNotIn("learner_memory", data)
            self.assertEqual(
                json.loads((Path(directory) / "memory-error.json").read_text())[
                    "error"
                ],
                "ValueError",
            )
        self.assertEqual(packet["topic"], "names")


if __name__ == "__main__":
    unittest.main()
