import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import sync

memory = sync.memory
NOW = datetime(2026, 11, 14, 22, 0, tzinfo=memory.TZ)
TOKEN = "a" * 32
STATE = {
    "sent": [
        {
            "token": TOKEN,
            "sent_at": "2026-11-11T09:24:00+03:00",
            "answered": True,
            "packet": {
                "title": "Values | names",
                "topic": "python.basics.values",
                "kind": "unaided_concept_check",
                "lesson": "An assignment gives a name to a value.",
                "question": "What does this print?",
                "resources": [
                    {"title": "Tutorial", "url": "https://docs.python.org/3/tutorial/"}
                ],
            },
        },
        {
            "token": "b" * 32,
            "sent_at": "2026-11-11T12:00:00+03:00",
            "packet": {
                "title": "Strings",
                "topic": "python.basics.strings",
                "kind": "unaided_concept_check",
                "lesson": "Text.",
                "question": "Slice it.",
            },
        },
    ],
    "assessments": [
        {
            "question_token": TOKEN,
            "at": "2026-11-11T11:00:00+03:00",
            "response_type": "answer",
            "score": 2,
            "assistance": "none",
            "learner_text": "6, because apples is rebound.",
            "feedback": "Correct.",
            "golden_answer": "6",
            "misconceptions": ["= compares"],
        }
    ],
}
DAY = {
    "day": 1,
    "title": "A support ticket, by hand",
    "topics": ["python.basics.values"],
    "status": "assigned",
    "score": None,
}


def repo_with(days, readme=f"# Title\n\n{sync.START}\nold\n{sync.END}\n\nfooter\n"):
    directory = tempfile.TemporaryDirectory()
    repo = Path(directory.name)
    (repo / "memory").mkdir()
    (repo / "memory/days.json").write_text(json.dumps(days))
    (repo / "README.md").write_text(readme)
    (repo / "state").mkdir()
    (repo / "state/state.json").write_text(json.dumps(STATE))
    return directory, repo


class ExportTests(unittest.TestCase):
    def test_export_writes_profile_lessons_and_dashboard(self):
        directory, repo = repo_with([DAY])
        with directory:
            (repo / "memory/lessons").mkdir()
            (repo / "memory/lessons/999-stale.md").write_text("stale")
            result = sync.export(repo, repo / "state", NOW)
            self.assertEqual(result, {"lessons": 2, "topics": 1, "days": 1})
            profile = json.loads((repo / "memory/profile.json").read_text())
            self.assertEqual(
                profile["topics"]["python.basics.values"]["latest_score"], 2
            )
            names = sorted(p.name for p in (repo / "memory/lessons").iterdir())
            self.assertEqual(
                names, ["001-python-basics-values.md", "002-python-basics-strings.md"]
            )
            answered = (repo / "memory/lessons" / names[0]).read_text()
            for expected in (
                "## Answer · 2/3",
                "6, because apples is rebound.",
                "### Golden answer",
                "- = compares",
                "[Tutorial]",
            ):
                self.assertIn(expected, answered)
            self.assertIn(
                "_Not answered yet._", (repo / "memory/lessons" / names[1]).read_text()
            )
            readme = (repo / "README.md").read_text()
            self.assertTrue(
                readme.startswith("# Title") and readme.endswith("footer\n")
            )
            self.assertNotIn("old", readme)
            self.assertIn("| 2 | 1 / 2 | 1 | 0 / 1 | 1 | 1 |", readme)
            self.assertIn(
                "| [01](days/day01/) | A support ticket, by hand | `values` | Assigned | – | – |",
                readme,
            )
            self.assertIn(
                "| `python.basics.values` | Practiced | 2/3 | 1 | 2026-11-12 · due |",
                readme,
            )
            self.assertIn("- = compares (seen 1×, `python.basics.values`)", readme)

    def test_export_is_idempotent_and_handles_an_empty_course(self):
        directory, repo = repo_with([])
        with directory:
            (repo / "state/state.json").unlink()
            sync.export(repo, repo / "state", NOW)
            first = (repo / "README.md").read_text()
            sync.export(repo, repo / "state", NOW)
            self.assertEqual(first, (repo / "README.md").read_text())
            self.assertIn("No scored attempts yet", first)

    def test_reviewed_day_links_its_review_and_unscored_reply_is_labelled(self):
        day = {
            **DAY,
            "status": "reviewed",
            "score": 3,
            "completed": "2026-11-12",
            "assistance": "none",
        }
        block = sync.dashboard(
            memory.build(STATE, [day]), [day], NOW + timedelta(days=30)
        )
        self.assertIn("| Reviewed | 3/3 | [notes](days/day01/REVIEW.md) |", block)
        reply = {
            **STATE["assessments"][0],
            "response_type": "clarification",
            "score": None,
            "golden_answer": "",
            "misconceptions": [],
        }
        text = sync.lesson_markdown(1, STATE["sent"][0], [reply])
        self.assertIn("## Clarification", text)
        self.assertNotIn("Golden answer", text)

    def test_readme_without_markers_is_rejected(self):
        directory, repo = repo_with([], readme="# Title\n")
        with directory, self.assertRaises(ValueError):
            sync.export(repo, repo / "state", NOW)


class PublishTests(unittest.TestCase):
    def test_commits_only_memory_and_readme_and_reports_unchanged(self):
        directory, repo = repo_with([DAY])
        with directory:
            for command in (
                ["init", "-q"],
                ["config", "user.email", "t@example.com"],
                ["config", "user.name", "T"],
            ):
                sync.git(repo, *command)
            (repo / "other.txt").write_text("unrelated work in progress")
            sync.git(repo, "add", "other.txt")
            self.assertEqual(
                sync.main(
                    ["--repo", str(repo), "--state", str(repo / "state"), "--commit"]
                )["git"],
                "committed",
            )
            committed = sync.git(
                repo, "show", "--name-only", "--format=%s", "HEAD"
            ).stdout
            self.assertIn("memory: sync", committed)
            self.assertIn("memory/profile.json", committed)
            self.assertNotIn("other.txt", committed)
            self.assertEqual(sync.publish(repo, "2026-11-14", False), "unchanged")
            (repo / "memory/days.json").write_text("[]")
            with self.assertRaises(subprocess.CalledProcessError):
                sync.publish(repo, "2026-11-14", True)


if __name__ == "__main__":
    unittest.main()
