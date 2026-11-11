# Days

One timed assignment per study day. Each folder is self-contained:

| File            | Purpose                                                                     |
| :-------------- | :-------------------------------------------------------------------------- |
| `README.md`     | The brief: scenario, time box, rules, tasks                                 |
| `solution.py`   | Stubs to fill in. This is the only file you edit, besides the notes         |
| `test_dayNN.py` | The specification as tests. Untouched functions skip, wrong ones fail       |
| `NOTES.md`      | Times, help used, predictions, what felt slow                               |
| `REVIEW.md`     | Written after submission: score, strengths, gaps, what Day N+1 will pick up |

Run one day:

```bash
python3 -m unittest discover -s days/day01 -v
```

The current list of days, with status and scores, is in the [progress table](../README.md#progress). How a day is assigned and reviewed is described in [`AGENTS.md`](../AGENTS.md).
