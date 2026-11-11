"""Build the private, offline coaching library; never sends or edits learning state."""

import argparse
import html
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path.home() / "Library/Application Support/PythonFDECoach"
TZ = ZoneInfo("Europe/Istanbul")


def read_state(path):
    return (
        json.loads(path.read_text()) if path.exists() else {"sent": [], "pending": None}
    )


def entries(root):
    sources = [("current", "Current course", root / "state.json")]
    sources += [
        ("archive", "Previous course", p)
        for p in sorted((root / "history").glob("*/state.json"))
    ]
    result = []
    for course, label, path in sources:
        state = read_state(path)
        result += [
            {**item, "_course": course, "_label": label, "_delivered": True}
            for item in state.get("sent", [])
        ]
        if state.get("pending"):
            result.append(
                {
                    **state["pending"],
                    "_course": course,
                    "_label": label,
                    "_delivered": False,
                }
            )
    return sorted(
        result,
        key=lambda item: (
            item["_course"] == "current",
            item.get("sent_at") or item.get("attempted_at") or "",
        ),
        reverse=True,
    )


def lesson_id(item):
    identity = (
        item.get("token")
        or item.get("message_id")
        or json.dumps(
            {k: item.get(k) for k in ("subject", "text_body", "packet")}, sort_keys=True
        )
    )
    return "lesson-" + hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:24]


def card(item):
    esc = html.escape
    identifier = lesson_id(item)
    packet = item.get("packet") or {}
    title = str(packet.get("title") or item.get("subject") or "Coaching email")
    topic = str(packet.get("topic") or "General")
    stamp = str(item.get("sent_at") or item.get("attempted_at") or "")
    date = stamp[:10]
    status = "Delivered" if item["_delivered"] else "Not confirmed delivered"
    body = item.get("text_body") or "\n\n".join(
        str(packet.get(k, "")) for k in ("title", "lesson", "question")
    )
    return f"""<article class="lesson" data-course="{item['_course']}" data-topic="{esc(topic, quote=True)}" data-date="{esc(date, quote=True)}">
<details id="{identifier}"><summary><div class="meta"><span>{esc(item['_label'])}</span><span>{esc(date or 'Awaiting delivery')}</span><span class="{'sent' if item['_delivered'] else 'pending'}">{status}</span></div>
<h2>{esc(title)}</h2><div class="topic">{esc(topic)} <span aria-hidden="true">↗</span></div></summary>
<div class="body"><pre>{esc(str(body))}</pre><a class="permalink" href="#{identifier}">Link to this lesson</a></div></details></article>"""


STYLE = """
:root{--ink:#183c38;--muted:#607773;--teal:#146e63;--paper:#f6f7f2;--line:#dce4db}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1100px;margin:auto;padding:38px 32px 80px}nav{display:flex;justify-content:space-between;gap:16px;font-size:12px;letter-spacing:.12em;text-transform:uppercase;border-bottom:1px solid var(--line);padding-bottom:20px}.brand{font-weight:800}.private{color:var(--muted)}header{padding:52px 0 32px;max-width:820px}.eyebrow{color:var(--teal);text-transform:uppercase;letter-spacing:.14em;font-size:12px;font-weight:700}h1{font-family:Georgia,serif;font-size:clamp(38px,6vw,66px);font-weight:400;line-height:1.1;letter-spacing:-.04em;margin:14px 0 20px}header p{font-size:18px;color:var(--muted);max-width:620px}.stats{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--line);background:#fff;border-radius:15px;margin:12px 0 34px}.stat{padding:22px 28px;border-right:1px solid var(--line)}.stat:last-child{border:0}.stat strong{display:block;font:32px Georgia,serif}.stat span{color:var(--muted);font-size:13px}.tools{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:12px;margin-bottom:16px}label{font-size:12px;font-weight:650;color:var(--muted)}input,select{width:100%;display:block;margin-top:6px;padding:12px;border:1px solid #cbd7cd;border-radius:8px;background:white;color:var(--ink);font:inherit;font-size:14px}input:focus,select:focus,summary:focus-visible{outline:3px solid #87c3b3;outline-offset:2px}.results{font-size:13px;color:var(--muted);margin-bottom:18px}.lesson{border:1px solid var(--line);border-radius:12px;background:white;margin:12px 0;overflow:hidden}summary{cursor:pointer;list-style:none;padding:24px 28px}summary::-webkit-details-marker{display:none}.meta{display:flex;flex-wrap:wrap;gap:12px;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}.sent{color:var(--teal)}.pending{color:#965b1b}h2{font-size:20px;line-height:1.4;font-weight:650;margin:10px 0}.topic{font-size:12px;color:var(--teal)}.topic span{float:right;font-size:22px}.body{border-top:1px solid var(--line);padding:24px 28px;background:#fcfdf9}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0;color:#29433e}.permalink{display:inline-block;margin-top:20px;color:var(--teal);font-size:12px}.empty{padding:40px;text-align:center;color:var(--muted);border:1px dashed #c4d1c4;border-radius:12px}footer{margin-top:36px;padding-top:22px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}[hidden]{display:none!important}@media(max-width:700px){main{padding:22px 18px 50px}header{padding-top:30px}.tools{grid-template-columns:1fr 1fr}.stats .stat{padding:16px 12px}.stat strong{font-size:25px}summary,.body{padding:20px}.private{letter-spacing:0}nav{font-size:10px}}
"""
SCRIPT = """
const cards=[...document.querySelectorAll('.lesson')];
const search=document.querySelector('#search'),course=document.querySelector('#course'),topic=document.querySelector('#topic'),date=document.querySelector('#date');
function filter(){let visible=0;for(const card of cards){const matches=(!search.value||card.textContent.toLowerCase().includes(search.value.toLowerCase()))&&(!course.value||card.dataset.course===course.value)&&(!topic.value||card.dataset.topic===topic.value)&&(!date.value||card.dataset.date===date.value);card.hidden=!matches;if(matches)visible++;}document.querySelector('#results').textContent=visible+' email'+(visible===1?'':'s')+' shown';document.querySelector('#no-results').hidden=visible!==0;}
for(const control of [search,course,topic,date])control.addEventListener('input',filter);
function reveal(){const id=location.hash.slice(1);const target=document.getElementById(id);if(target&&target.tagName==='DETAILS'){course.value='';topic.value='';date.value='';search.value='';filter();target.open=true;target.scrollIntoView();}}
window.addEventListener('hashchange',reveal);filter();reveal();
"""


def render(items):
    esc = html.escape
    delivered = sum(item["_delivered"] for item in items)
    current = sum(item["_delivered"] and item["_course"] == "current" for item in items)
    topics = sorted(
        {str((item.get("packet") or {}).get("topic") or "General") for item in items}
    )
    options = "".join(
        f'<option value="{esc(topic, quote=True)}">{esc(topic)}</option>'
        for topic in topics
    )
    now = datetime.now(TZ).strftime("%d %B %Y · %H:%M Istanbul")
    cards = "".join(card(item) for item in items)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Python learning library</title><style>{STYLE}</style></head><body><main>
<nav><span class="brand">Python / Learning library</span><span class="private">Private · Saved on this Mac</span></nav>
<header><div class="eyebrow">A little practice, every day</div><h1>Your Python<br>learning library.</h1><p>Every delivered lesson, in one quiet place. Revisit an example, find a topic, and pick up where you left off.</p></header>
<section class="stats" aria-label="Library overview"><div class="stat"><strong>{delivered}</strong><span>Delivered emails</span></div><div class="stat"><strong>{current}</strong><span>In your current course</span></div><div class="stat"><strong>15:00</strong><span>Daily Safari opening</span></div></section>
<section aria-label="Find a lesson"><div class="tools"><label>Search your library<input id="search" type="search" placeholder="Try a topic, title, or code snippet"></label><label>Course<select id="course"><option value="">All courses</option value="current">Current course</option><option value="archive">Previous courses</option></select></label><label>Topic<select id="topic"><option value="">All topics</option>{options}</select></label><label>Delivery date<input id="date" type="date"></label></div><div id="results" class="results" aria-live="polite"></div></section>
<section aria-label="Emails">{cards}<div class="empty" id="no-results">{'No emails match these filters.' if items else 'Your fresh start. Delivered lessons will appear here automatically.'}</div></section>
<footer>Updated {esc(now)}. Full email text is preserved below each title. Items marked “Not confirmed delivered” are retained for reference and do not count as delivered emails. Reload this page to see newly saved lessons.</footer>
</main><script>{SCRIPT}</script></body></html>"""


def build(root=ROOT):
    root = Path(root)
    content = render(entries(root))
    directory = root / "portal"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / "index.html"
    descriptor, temporary = tempfile.mkstemp(prefix=".portal-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "open"])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    path = build(args.root)
    if args.command == "open":
        subprocess.run(["/usr/bin/open", "-a", "Safari", str(path)], check=True)
    print(path)


if __name__ == "__main__":
    main()
