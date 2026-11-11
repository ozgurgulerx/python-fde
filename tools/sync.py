"""Export the coach's memory into this repository and refresh the README dashboard.

Reads the coach state read-only, writes `memory/` and the progress block in
README.md, and optionally commits and pushes those two paths. It never sends
mail, never edits coach state and never executes learner code.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATE = Path.home() / "Library/Application Support/PythonFDECoach"
sys.path.insert(0, str(REPO / "coach/scripts"))
import memory  # noqa: E402

START, END = "<!-- progress:start -->", "<!-- progress:end -->"
STATUS = {
    "assigned": "Assigned",
    "submitted": "Submitted",
    "reviewed": "Reviewed",
    "practiced": "Practiced",
    "independent": "Independent",
    "retained": "Retained",
}


def load_state(root):
    path = Path(root) / "state.json"
    return (
        json.loads(path.read_text())
        if path.exists()
        else {"sent": [], "assessments": []}
    )


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "lesson"


def lesson_markdown(number, item, assessments):
    packet = item["packet"]
    lines = [
        f"# Lesson {number:03d} · {packet['title']}",
        "",
        f"`{packet['topic']}` · {packet.get('kind', '')} · sent {memory.when(item['sent_at']).date().isoformat()}",
        "",
        packet["lesson"],
    ]
    if packet.get("question"):
        lines += ["", "## Question", "", packet["question"]]
    if packet.get("resources"):
        lines += ["", "## Resources", ""] + [
            f"- [{r['title']}]({r['url']})" for r in packet["resources"]
        ]
    for a in assessments:
        scored = a.get("score") is not None
        heading = (
            f"Answer · {a['score']}/3"
            if scored
            else a.get("response_type", "reply").replace("_", " ").title()
        )
        lines += [
            "",
            f"## {heading}",
            "",
            f"Assistance: {a.get('assistance', 'none')} · {memory.when(a['at']).date().isoformat()}",
        ]
        lines += ["", "### What I wrote", "", a.get("learner_text", "").strip()]
        lines += ["", "### Feedback", "", a.get("feedback", "").strip()]
        if a.get("golden_answer", "").strip():
            lines += ["", "### Golden answer", "", a["golden_answer"].strip()]
        if a.get("misconceptions"):
            lines += ["", "### Misconceptions", ""] + [
                f"- {m}" for m in a["misconceptions"]
            ]
    if packet.get("question") and not assessments:
        lines += ["", "_Not answered yet._"]
    return "\n".join(lines) + "\n"


def write_lessons(repo, state):
    folder = Path(repo) / "memory/lessons"
    folder.mkdir(parents=True, exist_ok=True)
    wanted = {}
    for number, item in enumerate(state.get("sent", []), 1):
        replies = [
            a
            for a in state.get("assessments", [])
            if a.get("question_token") == item["token"]
        ]
        wanted[f"{number:03d}-{slug(item['packet']['topic'])}.md"] = lesson_markdown(
            number, item, replies
        )
    for path in folder.glob("*.md"):
        if path.name not in wanted:
            path.unlink()
    for name, text in wanted.items():
        (folder / name).write_text(text)
    return len(wanted)


def dashboard(profile, days, now):
    totals, topics = profile["totals"], profile["topics"]
    due = memory.reviews_due(profile, now)
    open_items = [m for m in profile["misconceptions"] if m["status"] == "open"]
    lines = [
        "| Lessons sent | Questions answered | Scored attempts | Days reviewed | Reviews due | Open misconceptions |",
        "| :---: | :---: | :---: | :---: | :---: | :---: |",
        f"| {totals['lessons_sent']} | {totals['questions_answered']} / {totals['questions_asked']} "
        f"| {totals['scored_attempts']} | {totals['days_reviewed']} / {totals['days_assigned']} "
        f"| {len(due)} | {len(open_items)} |",
        "",
        "### Days",
        "",
        "| Day | Assignment | Topics | Status | Score | Review |",
        "| :-- | :-- | :-- | :-- | :-: | :-- |",
    ]
    for day in days:
        name = f"day{day['day']:02d}"
        score = f"{day['score']}/3" if day.get("score") is not None else "–"
        review = (
            f"[notes](days/{name}/REVIEW.md)"
            if day.get("status") == "reviewed"
            else "–"
        )
        topic_list = ", ".join(
            f"`{t.rsplit('.', 1)[-1]}`" for t in day.get("topics", [])
        )
        lines.append(
            f"| [{day['day']:02d}](days/{name}/) | {cell(day['title'])} | {topic_list} "
            f"| {STATUS.get(day.get('status'), day.get('status', ''))} | {score} | {review} |"
        )
    lines += ["", "### Topics", ""]
    if topics:
        lines += [
            "| Topic | Status | Latest | Attempts | Next review |",
            "| :-- | :-- | :-: | :-: | :-- |",
        ]
        overdue = {item["topic"] for item in due}
        for topic, record in topics.items():
            flag = " · due" if topic in overdue else ""
            lines.append(
                f"| `{cell(topic)}` | {STATUS[record['status']]} | {record['latest_score']}/3 "
                f"| {record['attempts']} | {record['next_review'][:10]}{flag} |"
            )
    else:
        lines.append(
            "_No scored attempts yet. This table fills in as answers and days are reviewed._"
        )
    if open_items:
        lines += ["", "### Open misconceptions", ""]
        lines += [
            f"- {m['text']} (seen {m['count']}×, {', '.join(f'`{t}`' for t in m['topics'])})"
            for m in open_items
        ]
    lines += [
        "",
        f"<sub>Last synced {now.date().isoformat()} by `tools/sync.py`.</sub>",
    ]
    return "\n".join(lines)


def update_readme(repo, block):
    path = Path(repo) / "README.md"
    text = path.read_text()
    if START not in text or END not in text:
        raise ValueError("README.md has no progress markers")
    head, rest = text.split(START, 1)
    path.write_text(f"{head}{START}\n{block}\n{END}{rest.split(END, 1)[1]}")


def export(repo, state_root, now):
    state, days = load_state(state_root), memory.load_days(repo)
    profile = memory.build(state, days)
    (Path(repo) / "memory").mkdir(exist_ok=True)
    (Path(repo) / "memory/profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    )
    lessons = write_lessons(repo, state)
    update_readme(repo, dashboard(profile, days, now))
    return {"lessons": lessons, "topics": len(profile["topics"]), "days": len(days)}


def git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=check, capture_output=True, text=True
    )


def publish(repo, day, push):
    paths = ["memory", "README.md"]
    git(repo, "add", "--", *paths)
    if (
        git(repo, "diff", "--cached", "--quiet", "--", *paths, check=False).returncode
        == 0
    ):
        return "unchanged"
    git(repo, "commit", "-m", f"memory: sync {day}", "--only", "--", *paths)
    if push:
        git(repo, "push")
        return "pushed"
    return "committed"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="commit memory/ and README.md if they changed",
    )
    parser.add_argument("--push", action="store_true", help="push after committing")
    args = parser.parse_args(argv)
    now = datetime.now(memory.TZ)
    result = export(args.repo, args.state, now)
    if args.commit or args.push:
        result["git"] = publish(args.repo, now.date().isoformat(), args.push)
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    main()
