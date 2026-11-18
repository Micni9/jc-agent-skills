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
| `field-add` / `field-list` / `field-update` / `field-remove` | per-list custom fields, see "Custom (sparse) fields" below; set values with `add`/`update --set name=value` |
| `drop-list` | delete a whole list |
| `backup` / `restore` | `lists.py backup <dest> [--force]`, `lists.py restore <file> [--force]`, see "Backup and recovery" below |
| `path` / `init` | print resolved DB path / create DB |

Viewer:

```bash
python scripts/view.py                 # all lists, open items, ordered by number
python scripts/view.py todo --status all
python scripts/view.py --lists
python scripts/view.py todo --json
```

## Schema

`lists(id, name UNIQUE, description, created_at)` and `items(id, list_id, number, title, status open|done, priority, location, note, extra, created_at, updated_at, done_at)` with `UNIQUE(list_id, number)`. `number` is the list number users refer to ("item 3"); it is stable across edits and only changes via `move` / `renumber`.

### Custom (sparse) fields per list

Data with no built-in column goes into per-list custom fields, stored in two extra tables:

- `list_fields(id, list_id, name, type text|int|real|bool|date, description, created_at)`, `UNIQUE(list_id, name)` - which extra fields each list has. Different lists can define different fields.
- `item_field_values(item_id, field_id, value)`, `PRIMARY KEY(item_id, field_id)` - one row only for a field that is actually set on an item (sparse: no row = unset). `value` is untyped so ints/reals sort numerically. Deleting an item, a field, or a list cascades to its values.

```bash
lists.py field-add todo severity --type int --desc "1-5"   # define once per list
lists.py add todo "Fix NPE" --set severity=4 --set owner=jc --auto-field   # --auto-field defines unknown names as text
lists.py update todo 3 --set severity=5 --unset owner
lists.py field-list todo                                   # name, type, used-count, description
lists.py field-update todo owner --rename assignee         # type change is refused once values exist
lists.py field-remove todo owner                           # also deletes its values
```

Values are validated against the field type (`int`, `real`, `bool` = true/false/yes/no/1/0, `date` = YYYY-MM-DD); a bad value or an undefined field aborts the whole command with nothing written. `list`/`view.py`/`show` print set fields; `--json` returns them under `"fields"`. Prefer custom fields over the free-form `extra` column. DBs created before this feature get the two tables on the next write; read-only commands work on old DBs unchanged.

## Backup and recovery

`.ai/lists.db` is usually git-ignored, so it may be the only copy of the data. Back it up outside the repo.

```bash
lists.py backup ~/backups/lists-2026-11-18.db            # consistent copy of the resolved DB
lists.py backup ~/backups/lists-latest.db --force        # replace an existing backup file
lists.py restore ~/backups/lists-2026-11-18.db           # target DB missing -> restored
lists.py restore ~/backups/lists-2026-11-18.db --force   # target DB exists -> replaced (see below)
lists.py --db other.db backup ...                        # --db / LIST_DB apply as everywhere else
```

Behaviour:

- `backup` uses the SQLite online backup API from a read-only connection, so it is safe while another process has the DB open (it captures committed data only, never a half-written file). It writes `<dest>.tmp`, runs `PRAGMA integrity_check` on it and only then renames it to `<dest>`; a failed backup leaves any existing destination untouched and no `.tmp` behind.
- `backup` refuses a missing source DB (it never creates one), a destination equal to the source, and an existing destination unless `--force`.
- `restore` validates the source first (opens, `integrity_check`, `lists`/`items` tables present, no foreign-key violations). If validation fails nothing is touched.
- `restore` refuses to replace an existing DB without `--force`. With `--force` it first saves the current DB as `<db>.pre-restore-<timestamp>.bak` (next to the DB), then copies the backup in through the backup API and applies additive schema migrations, so a backup made by an older version of the skill still works.
- Lists, item numbers/order/status/timestamps and custom field definitions and values are all preserved (the whole DB file content is copied).
- Only pass `--force` to `restore` when the user asked to replace the current DB, and tell them where the `.pre-restore-*.bak` copy is.

Cadence: back up before risky operations (`drop-list`, `restore --force`, bulk `remove`/`renumber`, schema/skill upgrades) and at least weekly while the list is in active use, to a directory that is synced or on another disk, with a dated file name so older backups are kept. After a restore, verify with `lists.py lists` and `view.py <list> --status all`.

## Working rules

1. One named list per concern (`todo`, `backlog`, `review-findings`, ...). Pick the name; reuse an existing one (`lists.py lists`) rather than creating near-duplicates.
2. Check for duplicates with `list --status all` before `add`.
3. Refer to items to the user as `<list> #<number>`.
4. Never write to the `.db` with ad-hoc SQL when a command exists; for reads beyond the viewer, open it read-only.
5. After changes, show the user `view.py <list>` output (or a summary) so they see the final order.
6. A project's own rules (`AGENTS.md`) that name a different store (e.g. `TODO.md` via `todo-tracking`) take precedence for that project; otherwise this skill applies.
7. Do not delete the DB or drop lists without being asked.

## Migrating an existing TODO.md / checklist into the DB

When the user asks to switch a project over:

1. `lists.py path`, then `add` each entry to one list (`todo`) in the original order, so numbers match reading order. Map priority to `--priority`, file refs to `--location`, description to `--note`.
2. Keep fields with no column (legacy ID such as `TODO-0001`, discovery date) as custom fields: `lists.py field-add todo legacy_id`, `field-add todo found --type date`, then `add ... --set legacy_id=TODO-0001 --set found=2026-11-04` (or `--auto-field` to define them as text on the fly).
3. Verify with `view.py <list> --status all` against the old file before removing it; delete the old file only when the user said "move" (it is usually untracked, so deletion is not recoverable from git).
4. Edit the project's agent-instructions TODO section (the same file rule 6 refers to) so it names this skill, the script path and the list name, and says the old store is retired; otherwise other agents keep writing to the old file. Preserve the file's existing line endings (CRLF is common on Windows).
5. Only add `.ai/` to the repo `.gitignore` if the user asks (see above); `.ai/` may already be self-ignored by its own `.gitignore`.

## Upgrading an existing DB after the skill changes

Adjust the existing DB in place; do not rebuild it (a rebuild loses ids, timestamps and done history, and additive schema changes migrate themselves on the next write).

1. `diff -ru --exclude=__pycache__` the project copy against the shared copy to see what changed; a whole-file diff is usually CRLF vs LF only, so read the real differences.
2. Move data that was parked in the free-form `extra` column (e.g. legacy ID, discovery date) into custom fields: `field-add <list> <name> [--type ...]` once per field, then `update <list> <n> --set name=value ... --extra ""` per item, so nothing is left in two places.
3. Verify with `show <list> <n>`, `field-list <list>` and `view.py <list> --status all`.

## Committing the skill itself

`scripts/__pycache__/` appears after the first run and is not ignored by default. Stage the files explicitly (`README.md`, `SKILL.md`, `scripts/*.py`) instead of `git add skills/list-sqlite`, and never commit `.pyc` or the `.db`. Keep skill changes and the project's `AGENTS.md` TODO-rule change in separate commits. If asked to ignore `__pycache__`, add `__pycache__/` to the repo `.gitignore` and confirm with `git check-ignore -v`; commit `.gitignore` only when asked.

If a copy of this skill already exists in the target `skills/` dir, `diff -rq --exclude=__pycache__ <src> <dst>` before copying; identical means nothing to do.

## Changing the scripts or SKILL.md

The skill lives in several copies: the source repo (`projects/jc-agent-skills/skills/list-sqlite`), `~/.agents/skills/list-sqlite` (shared, read by Hermes) and `~/.claude/skills/list-sqlite`. Other sessions edit them independently, so:

1. `diff -rq --exclude=__pycache__` all copies BEFORE editing. If a copy has content the source lacks, merge it into the source first (a whole-file diff usually just means CRLF vs LF; compare with line endings normalized) - copying source over it would silently drop that work.
2. Edit the source, then copy to the other two and re-run `diff -rq`; delete `__pycache__` afterwards (running a script from a copy recreates it).
3. Schema changes must be additive: new tables go in `CREATE TABLE IF NOT EXISTS` inside `SCHEMA` so existing DBs migrate on the next write. Every read path (`view.py`, `list`, `show`, `field-list`) opens the DB `mode=ro` and cannot create tables, so guard queries on new tables with a `sqlite_master` check (`has_field_tables`) instead of assuming they exist.
4. Multi-step writes (item row + custom-field values) run inside one `with con:` transaction so validation errors leave nothing behind and burn no list numbers.
5. Smoke-test in a scratch git repo run from a SUBDIRECTORY (proves repo-root detection puts `.ai/` at the root), and keep an old-schema DB copy to prove read-only commands still work on it.
6. For multi-line Python/file edits prefer `write_file`/`patch` over giant bash heredocs; a long heredoc with mixed quotes can abort the whole command with nothing written - check the file exists after a failed run.
