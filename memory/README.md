# Memory

Everything the coach knows about the course so far, as plain files. Git history of this folder is the progress record.

| Path           | Written by      | Contents                                                                                          |
| :------------- | :-------------- | :------------------------------------------------------------------------------------------------ |
| `profile.json` | `tools/sync.py` | Per-topic attempt history, review schedule, misconception ledger, reply-rate statistics           |
| `lessons/`     | `tools/sync.py` | One file per coaching email: lesson, question, and, once answered, the answer, score and feedback |
| `days.json`    | the day review  | Ledger of day assignments: status, time taken, help used, score, misconceptions                   |

`profile.json` and `lessons/` are generated from the coach's state and are overwritten on every sync, so edit `days.json` or the coach state, not those files.

## How a topic moves

| Status      | Meaning                                            |
| :---------- | :------------------------------------------------- |
| Introduced  | A lesson was sent, nothing scored yet              |
| Practiced   | At least one scored attempt                        |
| Independent | Two unaided attempts scored 2/3 or better          |
| Retained    | Independent, with the passes at least 7 days apart |

Scores run 0 to 3 per attempt. They are never averaged, and an attempt made with a hint, a scaffold, AI help or after seeing the solution never counts as an unaided pass.

## When a topic comes back

Each unaided pass moves the topic one step along `1 → 3 → 7 → 21` days. A miss or an assisted attempt sends it back to 1 day. When a review is due, the next lesson is a fresh task on that topic, not a repeat of the old question.

## Misconceptions

Each misconception recorded in a review is counted across every lesson and day. It stays open until two later unaided passes on one of its topics.
