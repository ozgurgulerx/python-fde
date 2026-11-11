# References

`first.json` is the first lesson of the course and the only reference file in the repository.

The coach also reads three files that are kept out of git because they hold personal context and material adapted from third-party interview reports:

| File                     | Shape                                                                                                                      | Used for                                                    |
| :----------------------- | :------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------- |
| `context.json`           | object with `target`, `curriculum` (list), `learning_rules` (list), `resources` (list of `{title, url, tags, checked_at}`) | goals, course order, and the only URLs a lesson may link to |
| `question-bank.json`     | list of `{id, topic, mode, prompt, variants, provenance}`                                                                  | practice prompts the lesson designer can draw on            |
| `interview-sources.json` | list of public pages checked by the weekly research job                                                                    | source registry for new practice themes                     |
| `private-notes.md`       | prose                                                                                                                      | operating notes that name specific companies                |

Without these files the tests still pass, but lesson generation and the research job will not run.
