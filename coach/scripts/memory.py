"""Derived learner memory: topic history, spaced reviews, misconceptions, engagement.

Pure functions over the coach state and the repository day ledger. This module
never sends mail, never edits coach state and never executes learner code. The
profile is practice evidence only; it makes no mastery claim.
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
LADDER = (1, 3, 7, 21)  # days until the next fresh check after each unaided pass
PASS = 2  # 0-3 scale: 2 is a sound answer, 3 a complete one
RETAIN_GAP = timedelta(days=7)  # distance between first and latest pass for "retained"
REPO = Path(
    os.environ.get(
        "PYTHON_FDE_REPO", str(Path.home() / "Developer/Projects/python-fde")
    )
)
POLICY = (
    "learner_memory summarises every assessed attempt in this course. When no "
    "assessment is outstanding and reviews_due is non-empty, prefer a fresh, "
    "distinct task on the most overdue topic instead of a new topic. Retest an "
    "open misconception with a new example, never the original question. Favour "
    "lesson kinds with a higher reply_rate; if unanswered_streak is 3 or more, "
    "make the next question shorter and easier to start. Recent day assignments "
    "are longer timed builds done in the repository: build on them, do not repeat "
    "them. All of this is practice evidence; never state or imply mastery."
)


def when(value):
    stamp = datetime.fromisoformat(value)
    return stamp.astimezone(TZ) if stamp.tzinfo else stamp.replace(tzinfo=TZ)


def unaided(assistance):
    return assistance in (None, "", "none")


def load_days(repo=None):
    path = Path(repo or REPO) / "memory/days.json"
    try:
        days = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return [d for d in days if isinstance(d, dict)] if isinstance(days, list) else []


def attempts(state, days=()):
    """Every scored attempt, oldest first, from email assessments and reviewed days."""
    sent = {item["token"]: item for item in state.get("sent", [])}
    found = []
    for a in state.get("assessments", []):
        origin = sent.get(a.get("question_token"))
        if a.get("response_type") != "answer" or a.get("score") is None or not origin:
            continue
        found.append(
            {
                "topic": origin["packet"]["topic"],
                "at": when(a["at"]).isoformat(),
                "score": a["score"],
                "assistance": a.get("assistance", "none"),
                "kind": origin["packet"].get("kind", ""),
                "source": "email",
                "ref": a["question_token"][:12],
                "misconceptions": list(a.get("misconceptions", [])),
            }
        )
    for day in days:
        if day.get("status") != "reviewed" or day.get("score") is None:
            continue
        for topic in day.get("topics", []):
            found.append(
                {
                    "topic": topic,
                    "at": when(day["completed"]).isoformat(),
                    "score": day["score"],
                    "assistance": day.get("assistance", "none"),
                    "kind": "day_assignment",
                    "source": "day",
                    "ref": f"day{day['day']:02d}",
                    "misconceptions": list(day.get("misconceptions", [])),
                }
            )
    return sorted(found, key=lambda item: item["at"])


def topic_record(history):
    """Spaced-review position for one topic from its ordered attempts."""
    step, passes, interval = 0, [], LADDER[0]
    for item in history:
        if unaided(item["assistance"]) and item["score"] >= PASS:
            interval = LADDER[min(step, len(LADDER) - 1)]
            step += 1
            passes.append(when(item["at"]))
        else:
            step, interval = 0, LADDER[0]
    last = history[-1]
    status = "practiced"
    if len(passes) >= 2:
        status = "retained" if passes[-1] - passes[0] >= RETAIN_GAP else "independent"
    return {
        "status": status,
        "attempts": len(history),
        "unaided_passes": len(passes),
        "latest_score": last["score"],
        "best_score": max(i["score"] for i in history),
        "latest_at": last["at"],
        "interval_days": interval,
        "next_review": (when(last["at"]) + timedelta(days=interval)).isoformat(),
        "history": [
            {k: i[k] for k in ("at", "score", "assistance", "source", "ref")}
            for i in history
        ],
    }


def normalise(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def misconception_ledger(found, topics):
    ledger = {}
    for item in found:
        for text in item["misconceptions"]:
            key = normalise(text)
            if not key:
                continue
            entry = ledger.setdefault(
                key,
                {
                    "text": text.strip(),
                    "count": 0,
                    "first_seen": item["at"],
                    "topics": [],
                },
            )
            entry["count"] += 1
            entry["last_seen"] = item["at"]
            if item["topic"] not in entry["topics"]:
                entry["topics"].append(item["topic"])
    for entry in ledger.values():
        later = [
            h
            for t in entry["topics"]
            for h in topics[t]["history"]
            if h["at"] > entry["last_seen"]
            and unaided(h["assistance"])
            and h["score"] >= PASS
        ]
        entry["status"] = "cleared" if len(later) >= 2 else "open"
    return sorted(
        ledger.values(),
        key=lambda e: (e["status"] != "open", -e["count"], e["first_seen"]),
    )


def engagement(state):
    kinds, hours, streak = {}, {}, 0
    for item in state.get("sent", []):
        asked = bool(item["packet"].get("question"))
        kind = kinds.setdefault(
            item["packet"].get("kind", ""), {"sent": 0, "asked": 0, "answered": 0}
        )
        kind["sent"] += 1
        if not asked:
            continue
        hour = hours.setdefault(
            f"{when(item['sent_at']).hour:02d}", {"asked": 0, "answered": 0}
        )
        kind["asked"] += 1
        hour["asked"] += 1
        if item.get("answered"):
            kind["answered"] += 1
            hour["answered"] += 1
            streak = 0
        else:
            streak += 1
    for bucket in kinds.values():
        bucket["reply_rate"] = (
            round(bucket["answered"] / bucket["asked"], 2) if bucket["asked"] else None
        )
    return {
        "by_kind": kinds,
        "by_hour": dict(sorted(hours.items())),
        "unanswered_streak": streak,
    }


def build(state, days=()):
    """Full profile. Deterministic for a given state and ledger: no clock reads."""
    found = attempts(state, days)
    grouped = {}
    for item in found:
        grouped.setdefault(item["topic"], []).append(item)
    topics = {
        topic: topic_record(history) for topic, history in sorted(grouped.items())
    }
    introduced = sorted(
        {item["packet"]["topic"] for item in state.get("sent", [])} - set(topics)
    )
    sent = state.get("sent", [])
    return {
        "version": 1,
        "course_started": when(sent[0]["sent_at"]).date().isoformat() if sent else None,
        "totals": {
            "lessons_sent": len(sent),
            "questions_asked": sum(bool(s["packet"].get("question")) for s in sent),
            "questions_answered": sum(bool(s.get("answered")) for s in sent),
            "scored_attempts": len(found),
            "days_assigned": len(days),
            "days_reviewed": sum(d.get("status") == "reviewed" for d in days),
        },
        "topics": topics,
        "introduced": introduced,
        "misconceptions": misconception_ledger(found, topics),
        "engagement": engagement(state),
    }


def reviews_due(profile, now):
    due = [
        {
            "topic": topic,
            "due": record["next_review"],
            "status": record["status"],
            "latest_score": record["latest_score"],
        }
        for topic, record in profile["topics"].items()
        if when(record["next_review"]) <= now
    ]
    return sorted(due, key=lambda item: item["due"])


def for_generator(state, now=None, repo=None):
    """Compact view handed to the lesson designer; bounded regardless of course length."""
    now = now or datetime.now(TZ)
    days = load_days(repo)
    profile = build(state, days)
    return {
        "policy": POLICY,
        "totals": profile["totals"],
        "topics": [
            {
                "topic": t,
                "status": r["status"],
                "latest_score": r["latest_score"],
                "attempts": r["attempts"],
                "next_review": r["next_review"][:10],
            }
            for t, r in profile["topics"].items()
        ][-60:],
        "reviews_due": reviews_due(profile, now)[:5],
        "open_misconceptions": [
            {"text": m["text"], "count": m["count"], "topics": m["topics"]}
            for m in profile["misconceptions"]
            if m["status"] == "open"
        ][:8],
        "engagement": profile["engagement"],
        "recent_days": [
            {k: d.get(k) for k in ("day", "title", "topics", "status", "score")}
            for d in days[-5:]
        ],
    }
