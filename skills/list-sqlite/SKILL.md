---
name: list-sqlite
description: Use when creating, updating or viewing a todo list, checklist, backlog, task queue, or any other list-shaped context. Stores it in a SQLite DB at <repo root>/.ai/lists.db (unless a path is given) and views it ordered by list number with a script. 管理待辦、清單、任何可用清單表示的資料時，改用 SQLite（預設 repo 根目錄 .ai/）維護，並以腳本依編號順序檢視。
---

# list-sqlite

Rule: **any todo, backlog, checklist, or other list-shaped context is kept in a SQLite database, not in a Markdown/JSON/text file or in your head.** The database is the source of truth; view it with the script.

## Where the DB lives

Resolution order (first hit wins):

1. `--db <path>` (user specified a file)
2. env `LIST_DB`
3. `<repo root>/.ai/lists.db` — repo root = nearest ancestor of cwd containing `.git` (dir or file); falls back to cwd if none. `.ai/` is created automatically.

If the user names a different `.db` location, pass it with `--db` on **every** call. Run `lists.py path` to confirm where it resolves before the first write.

Do not commit the `.db` or edit `.gitignore` unless asked. If `.ai/` is not ignored, mention it once.

## Scripts (relative to this SKILL.md; Python 3.8+, stdlib only)

```bash
python scripts/lists.py <command> ...   # read/write
python scripts/view.py [list] ...       # read-only viewer, always ordered by list number
```

`python` may be `python3` / `py` depending on the machine.

| Command | Example |
| --- | --- |
| `add` (auto-creates list, number = max+1) | `lists.py add todo "Fix NPE" --priority P1 --location src/A.java:42 --note "why"` |
| `list` | `lists.py list todo --status all` (`open` default, `done`, `all`; `--priority`, `--json`) |
| `lists` | names + open/total counts |
| `show` | `lists.py show todo 3` |
| `update` | `lists.py update todo 3 --priority P0 --note "..."` |
| `done` / `reopen` | `lists.py done todo 3` |
| `remove` | `lists.py remove todo 3 [--renumber]` (gap is kept unless `--renumber`) |
| `move` | `lists.py move todo 5 --to 1` (inserts, shifts the rest, renumbers 1..n) |
| `renumber` | compact numbers to 1..n, order preserved |
| `drop-list` | delete a whole list |
| `path` / `init` | print resolved DB path / create DB |

Viewer:

```bash
python scripts/view.py                 # all lists, open items, ordered by number
python scripts/view.py todo --status all
python scripts/view.py --lists
python scripts/view.py todo --json
```

## Schema

`lists(id, name UNIQUE, description, created_at)` and `items(id, list_id, number, title, status open|done, priority, location, note, extra, created_at, updated_at, done_at)` with `UNIQUE(list_id, number)`. `number` is the list number users refer to ("item 3"); it is stable across edits and only changes via `move` / `renumber`. Use `extra` for free-form or JSON data that has no column.

## Working rules

1. One named list per concern (`todo`, `backlog`, `review-findings`, ...). Pick the name; reuse an existing one (`lists.py lists`) rather than creating near-duplicates.
2. Check for duplicates with `list --status all` before `add`.
3. Refer to items to the user as `<list> #<number>`.
4. Never write to the `.db` with ad-hoc SQL when a command exists; for reads beyond the viewer, open it read-only.
5. After changes, show the user `view.py <list>` output (or a summary) so they see the final order.
6. A project's own rules (`AGENTS.md`) that name a different store (e.g. `TODO.md` via `todo-tracking`) take precedence for that project; otherwise this skill applies.
7. Do not delete the DB or drop lists without being asked.
