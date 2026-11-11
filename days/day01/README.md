# Day 01 · A support ticket, by hand

**Topics:** values and names, expressions, strings, conditionals, a first look at mutation
**Time box:** 30 minutes (5 predicting, 25 building)
**Mode:** unaided. No AI, no search. The Python docs are fine. If you do use help, write down what and where.

You have joined a support-desk team. Before any framework or API shows up, you need five small functions that turn raw ticket input into clean values. Nothing here needs an import.

## Part A · Predict (5 minutes, do not run anything)

Write your answers in [`NOTES.md`](NOTES.md) before you open a Python prompt. A one-line "why" matters more than the output.

**P1**

```python
price = 10
total = price
total = total + 5
print(price, total)
```

**P2**

```python
tags = ["billing"]
labels = tags
labels.append("vip")
print(tags)
```

**P3 (stretch)**

```python
def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags

print(add_tag("vip"))
print(add_tag("urgent"))
```

## Part B · Build (25 minutes)

Open [`solution.py`](solution.py) and replace each `raise NotImplementedError`. Each docstring is the specification.

|  #  | Function                                           | What it practises                         |
| :-: | :------------------------------------------------- | :---------------------------------------- |
|  1  | `line_total(unit_price, quantity, discount_pct=0)` | arithmetic, rounding, rejecting bad input |
|  2  | `ticket_ref(prefix, number)`                       | string methods and number formatting      |
|  3  | `clean_subject(raw)`                               | splitting, joining and slicing strings    |
|  4  | `priority(subject, is_vip=False)`                  | booleans and conditionals                 |
|  5  | `with_tag(tags, tag)`                              | a name versus the list it points to       |

Run the tests as often as you like:

```bash
python3 -m unittest discover -s days/day01 -v
```

A function you have not started shows as `skipped`. A wrong answer shows as a failure.

## Finish

1. Stop the clock at 30 minutes, even if something is unfinished. Unfinished is useful information.
2. Fill in the rest of [`NOTES.md`](NOTES.md): start and end time, any help used, what felt slow.
3. Commit and push:

   ```bash
   git add days/day01 && git commit -m "day01: support ticket functions" && git push
   ```

4. Ask for the review ("review day01"). The review goes in `REVIEW.md` here, your score and any misconceptions go into [`memory/`](../../memory/), and Day 02 is built from them.
