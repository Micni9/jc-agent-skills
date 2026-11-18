# list-sqlite

Keep todos and any other list-shaped context in SQLite instead of loose Markdown/JSON. Default DB: `<repo root>/.ai/lists.db`.

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Rules, commands, schema |
| `scripts/lists.py` | CRUD: add / list / show / update / done / reopen / remove / move / renumber / drop-list |
| `scripts/view.py` | Read-only viewer, ordered by list number |

```bash
python scripts/lists.py add todo "First item" --priority P1
python scripts/lists.py add todo "Second item"
python scripts/lists.py move todo 2 --to 1
python scripts/view.py todo
```

DB path: `--db <file>` > env `LIST_DB` > `<repo root>/.ai/lists.db` (repo root = nearest `.git` ancestor, else cwd).

Requires Python 3.8+ (stdlib `sqlite3`); no other dependencies.
