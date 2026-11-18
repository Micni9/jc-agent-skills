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

Backup and restore (SQLite backup API; never overwrites without `--force`, restore validates the file first and keeps a `.pre-restore-*.bak` of the current DB):

```bash
python scripts/lists.py backup ~/backups/lists-2026-11-18.db
python scripts/lists.py restore ~/backups/lists-2026-11-18.db --force
```

Per-list custom fields (sparse EAV tables `list_fields` + `item_field_values`):

```bash
python scripts/lists.py field-add todo severity --type int
python scripts/lists.py add todo "Fix NPE" --set severity=4
python scripts/view.py todo
```
