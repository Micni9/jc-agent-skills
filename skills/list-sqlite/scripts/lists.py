#!/usr/bin/env python3
"""SQLite-backed list manager (todo / checklist / any ordered list).

Python 3.8+, stdlib only. Default DB: <repo root>/.ai/lists.db
DB resolution order: --db > env LIST_DB > <repo root>/.ai/lists.db
Repo root = nearest ancestor of cwd containing .git (dir or file); fallback cwd.
"""
import argparse, json, os, sqlite3, sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  list_id    INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  number     INTEGER NOT NULL,
  title      TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done')),
  priority   TEXT,
  location   TEXT,
  note       TEXT,
  extra      TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  done_at    TEXT,
  UNIQUE (list_id, number)
);
CREATE INDEX IF NOT EXISTS idx_items_list_number ON items(list_id, number);

-- Per-list custom (sparse) field definitions.
CREATE TABLE IF NOT EXISTS list_fields (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  list_id     INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  type        TEXT NOT NULL DEFAULT 'text' CHECK (type IN ('text','int','real','bool','date')),
  description TEXT,
  created_at  TEXT NOT NULL,
  UNIQUE (list_id, name)
);
-- Sparse values: one row per (item, field) that is actually set.
-- `value` has no declared type on purpose: ints/reals stay numeric, so ORDER BY / comparisons work.
CREATE TABLE IF NOT EXISTS item_field_values (
  item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  field_id INTEGER NOT NULL REFERENCES list_fields(id) ON DELETE CASCADE,
  value,
  PRIMARY KEY (item_id, field_id)
);
CREATE INDEX IF NOT EXISTS idx_ifv_field ON item_field_values(field_id);
"""

FIELD_TYPES = ("text", "int", "real", "bool", "date")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def repo_root(start=None):
    cur = Path(start or os.getcwd()).resolve()
    for d in [cur, *cur.parents]:
        if (d / ".git").exists():
            return d
    return cur


def resolve_db(arg=None):
    p = arg or os.environ.get("LIST_DB")
    if p and p.strip():
        return Path(p).expanduser().resolve()
    return repo_root() / ".ai" / "lists.db"


def connect(db_path, readonly=False):
    db_path = Path(db_path)
    if readonly:
        if not db_path.exists():
            sys.exit(f"DB not found: {db_path}")
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(db_path)
        con.executescript(SCHEMA)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def get_list(con, name, create=False, desc=None):
    row = con.execute("SELECT * FROM lists WHERE name=?", (name,)).fetchone()
    if row:
        return row
    if not create:
        sys.exit(f"List not found: {name}")
    con.execute("INSERT INTO lists(name,description,created_at) VALUES(?,?,?)", (name, desc, now()))
    return con.execute("SELECT * FROM lists WHERE name=?", (name,)).fetchone()


def get_item(con, lst, number):
    row = con.execute("SELECT * FROM items WHERE list_id=? AND number=?", (lst["id"], number)).fetchone()
    if not row:
        sys.exit(f"Item not found: {lst['name']} #{number}")
    return row


def fetch_items(con, lst, status="open", priority=None):
    q, a = "SELECT * FROM items WHERE list_id=?", [lst["id"]]
    if status != "all":
        q += " AND status=?"
        a.append(status)
    if priority:
        q += " AND priority=?"
        a.append(priority)
    return con.execute(q + " ORDER BY number", a).fetchall()


def has_field_tables(con):
    n = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('list_fields','item_field_values')").fetchone()[0]
    return n == 2


def coerce(ftype, raw, fname=""):
    """Validate/normalize a CLI string for a field type."""
    try:
        if ftype == "int":
            return int(raw)
        if ftype == "real":
            return float(raw)
        if ftype == "bool":
            v = str(raw).strip().lower()
            if v in ("1", "true", "yes", "y"):
                return 1
            if v in ("0", "false", "no", "n"):
                return 0
            raise ValueError
        if ftype == "date":
            return datetime.strptime(str(raw).strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        sys.exit(f"Field '{fname}' expects {ftype}, got: {raw!r}")
    return str(raw)


def get_field(con, lst, name):
    row = con.execute("SELECT * FROM list_fields WHERE list_id=? AND name=?", (lst["id"], name)).fetchone()
    if not row:
        sys.exit(f"Field '{name}' not defined for list '{lst['name']}'. "
                 f"Define it: field-add {lst['name']} {name} [--type text|int|real|bool|date] "
                 f"(or pass --auto-field to create it as text).")
    return row


def apply_sets(con, lst, item_id, sets, unsets=(), auto_field=False):
    """sets: ['name=value', ...]; unsets: ['name', ...]. Writes sparse rows (no row = unset)."""
    for s in sets or ():
        if "=" not in s:
            sys.exit(f"--set expects name=value, got: {s!r}")
        name, raw = s.split("=", 1)
        name = name.strip()
        row = con.execute("SELECT * FROM list_fields WHERE list_id=? AND name=?", (lst["id"], name)).fetchone()
        if not row and auto_field:
            con.execute("INSERT INTO list_fields(list_id,name,type,created_at) VALUES(?,?,?,?)",
                        (lst["id"], name, "text", now()))
            row = con.execute("SELECT * FROM list_fields WHERE list_id=? AND name=?", (lst["id"], name)).fetchone()
        if not row:
            row = get_field(con, lst, name)  # exits with hint
        con.execute("INSERT OR REPLACE INTO item_field_values(item_id,field_id,value) VALUES(?,?,?)",
                    (item_id, row["id"], coerce(row["type"], raw, name)))
    for name in unsets or ():
        row = get_field(con, lst, name.strip())
        con.execute("DELETE FROM item_field_values WHERE item_id=? AND field_id=?", (item_id, row["id"]))


def load_values(con, item_ids):
    """{item_id: {field_name: value}} for the given items (sparse; only set fields)."""
    out = {i: {} for i in item_ids}
    if not item_ids or not has_field_tables(con):
        return out
    marks = ",".join("?" * len(item_ids))
    q = ("SELECT v.item_id, f.name, f.type, v.value FROM item_field_values v "
         "JOIN list_fields f ON f.id=v.field_id WHERE v.item_id IN (%s) ORDER BY f.id" % marks)
    for r in con.execute(q, list(item_ids)):
        out[r["item_id"]][r["name"]] = bool(r["value"]) if r["type"] == "bool" else r["value"]
    return out


def fmt_item(r, fields=None):
    box = "[x]" if r["status"] == "done" else "[ ]"
    pri = f" [{r['priority']}]" if r["priority"] else ""
    s = f"{r['number']:>3}. {box}{pri} {r['title']}"
    if r["location"]:
        s += f"  ({r['location']})"
    if fields:
        s += "\n       " + "  ".join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in fields.items())
    if r["note"]:
        s += "\n       " + r["note"].replace("\n", "\n       ")
    return s


def print_list(con, lst, status="open", priority=None, as_json=False):
    rows = fetch_items(con, lst, status, priority)
    vals = load_values(con, [r["id"] for r in rows])
    if as_json:
        out = []
        for r in rows:
            d = {"list": lst["name"], **{k: r[k] for k in r.keys() if k not in ("id", "list_id")}}
            d["fields"] = vals[r["id"]]
            out.append(d)
        return out
    print(f"# {lst['name']}" + (f" - {lst['description']}" if lst["description"] else ""))
    if not rows:
        print("(empty)")
    for r in rows:
        print(fmt_item(r, vals[r["id"]]))
    return None


def _set_numbers(con, ordered_ids):
    """Assign 1..n in the given order (two-phase to dodge UNIQUE collisions)."""
    for i, iid in enumerate(ordered_ids, 1):
        con.execute("UPDATE items SET number=? WHERE id=?", (-i, iid))
    for i, iid in enumerate(ordered_ids, 1):
        con.execute("UPDATE items SET number=? WHERE id=?", (i, iid))


def renumber(con, lst):
    ids = [r["id"] for r in con.execute("SELECT id FROM items WHERE list_id=? ORDER BY number", (lst["id"],))]
    _set_numbers(con, ids)


# ---- commands -------------------------------------------------------------
def cmd_path(a, db):
    print(db)


def cmd_init(a, db):
    connect(db).close()
    print(f"DB ready: {db}")


def cmd_add(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list, create=True, desc=a.list_desc)
        if a.number is None:
            num = con.execute("SELECT COALESCE(MAX(number),0)+1 FROM items WHERE list_id=?", (lst["id"],)).fetchone()[0]
        else:
            num = a.number
            if con.execute("SELECT 1 FROM items WHERE list_id=? AND number=?", (lst["id"], num)).fetchone():
                sys.exit(f"Number {num} already used in '{a.list}'. Use `move` to insert, or omit --number.")
        t = now()
        con.execute(
            "INSERT INTO items(list_id,number,title,priority,location,note,extra,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (lst["id"], num, a.title, a.priority, a.location, a.note, a.extra, t, t))
        item_id = con.execute("SELECT id FROM items WHERE list_id=? AND number=?", (lst["id"], num)).fetchone()[0]
        apply_sets(con, lst, item_id, a.set, auto_field=a.auto_field)  # error -> whole add rolls back
    print(f"Added {a.list} #{num}: {a.title}")


def cmd_list(a, db):
    con = connect(db, readonly=True)
    lst = get_list(con, a.list)
    out = print_list(con, lst, a.status, a.priority, a.json)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_lists(a, db):
    con = connect(db, readonly=True)
    for l in con.execute("SELECT * FROM lists ORDER BY name"):
        c = con.execute("SELECT SUM(status='open'), COUNT(*) FROM items WHERE list_id=?", (l["id"],)).fetchone()
        print(f"{l['name']}\topen={c[0] or 0}\ttotal={c[1]}\t{l['description'] or ''}")


def cmd_show(a, db):
    con = connect(db, readonly=True)
    lst = get_list(con, a.list)
    r = get_item(con, lst, a.number)
    for k in r.keys():
        if k not in ("id", "list_id") and r[k] is not None:
            print(f"{k}: {r[k]}")
    for k, v in load_values(con, [r["id"]])[r["id"]].items():
        print(f"field.{k}: {str(v).lower() if isinstance(v, bool) else v}")


def cmd_update(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        r = get_item(con, lst, a.number)
        sets = {k: v for k, v in (("title", a.title), ("priority", a.priority), ("location", a.location),
                                   ("note", a.note), ("extra", a.extra)) if v is not None}
        if not sets and not a.set and not a.unset:
            sys.exit("Nothing to update.")
        sets["updated_at"] = now()
        con.execute(f"UPDATE items SET {','.join(k + '=?' for k in sets)} WHERE id=?", [*sets.values(), r["id"]])
        apply_sets(con, lst, r["id"], a.set, a.unset, a.auto_field)
    print(f"Updated {a.list} #{a.number}")


def _status(a, db, status):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        r = get_item(con, lst, a.number)
        t = now()
        con.execute("UPDATE items SET status=?, done_at=?, updated_at=? WHERE id=?",
                    (status, t if status == "done" else None, t, r["id"]))
    print(f"{a.list} #{a.number} -> {status}")


def cmd_done(a, db):
    _status(a, db, "done")


def cmd_reopen(a, db):
    _status(a, db, "open")


def cmd_remove(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        r = get_item(con, lst, a.number)
        con.execute("DELETE FROM items WHERE id=?", (r["id"],))
        if a.renumber:
            renumber(con, lst)
    print(f"Removed {a.list} #{a.number}" + (" (renumbered)" if a.renumber else ""))


def cmd_move(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        r = get_item(con, lst, a.number)
        ids = [x["id"] for x in con.execute("SELECT id FROM items WHERE list_id=? ORDER BY number", (lst["id"],))]
        ids.remove(r["id"])
        ids.insert(max(0, min(a.to - 1, len(ids))), r["id"])
        _set_numbers(con, ids)
    print(f"Moved {a.list} #{a.number} to position {a.to} (list renumbered 1..{len(ids)})")


def cmd_renumber(a, db):
    con = connect(db)
    with con:
        renumber(con, get_list(con, a.list))
    print(f"Renumbered {a.list}")


def cmd_field_add(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        if con.execute("SELECT 1 FROM list_fields WHERE list_id=? AND name=?", (lst["id"], a.name)).fetchone():
            sys.exit(f"Field '{a.name}' already exists in '{a.list}'.")
        con.execute("INSERT INTO list_fields(list_id,name,type,description,created_at) VALUES(?,?,?,?,?)",
                    (lst["id"], a.name, a.type, a.desc, now()))
    print(f"Defined field {a.list}.{a.name} ({a.type})")


def cmd_field_list(a, db):
    con = connect(db, readonly=True)
    lst = get_list(con, a.list)
    if not has_field_tables(con):
        return
    q = ("SELECT f.*, (SELECT COUNT(*) FROM item_field_values v WHERE v.field_id=f.id) AS used "
         "FROM list_fields f WHERE f.list_id=? ORDER BY f.id")
    for f in con.execute(q, (lst["id"],)):
        print(f"{f['name']}\t{f['type']}\tused={f['used']}\t{f['description'] or ''}")


def cmd_field_update(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        f = get_field(con, lst, a.name)
        if a.rename:
            if con.execute("SELECT 1 FROM list_fields WHERE list_id=? AND name=?", (lst["id"], a.rename)).fetchone():
                sys.exit(f"Field '{a.rename}' already exists.")
            con.execute("UPDATE list_fields SET name=? WHERE id=?", (a.rename, f["id"]))
        if a.desc is not None:
            con.execute("UPDATE list_fields SET description=? WHERE id=?", (a.desc, f["id"]))
        if a.type and a.type != f["type"]:
            n = con.execute("SELECT COUNT(*) FROM item_field_values WHERE field_id=?", (f["id"],)).fetchone()[0]
            if n:
                sys.exit(f"Field '{a.name}' has {n} value(s); type change refused. "
                         f"Create a new field, copy values, then field-remove the old one.")
            con.execute("UPDATE list_fields SET type=? WHERE id=?", (a.type, f["id"]))
    print(f"Updated field {a.list}.{a.name}")


def cmd_field_remove(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        f = get_field(con, lst, a.name)
        n = con.execute("SELECT COUNT(*) FROM item_field_values WHERE field_id=?", (f["id"],)).fetchone()[0]
        con.execute("DELETE FROM list_fields WHERE id=?", (f["id"],))  # values cascade
    print(f"Removed field {a.list}.{a.name} (and {n} value(s))")


def cmd_drop_list(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        con.execute("DELETE FROM lists WHERE id=?", (lst["id"],))
    print(f"Dropped list {a.list}")


def _check_db_file(path, what):
    """Open `path` read-only and verify it is a healthy list-sqlite DB. Exits with a message otherwise."""
    path = Path(path)
    if not path.is_file():
        sys.exit(f"{what} not found: {path}")
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchall()
            if ok != [("ok",)]:
                sys.exit(f"{what} failed integrity_check: {path}: {ok[0][0]}")
            names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"lists", "items"} <= names:
                sys.exit(f"{what} is not a list-sqlite database (missing lists/items tables): {path}")
            if con.execute("PRAGMA foreign_key_check").fetchall():
                sys.exit(f"{what} has foreign key violations: {path}")
            n_lists = con.execute("SELECT COUNT(*) FROM lists").fetchone()[0]
            n_items = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        sys.exit(f"{what} is not a valid SQLite database: {path}: {e}")
    return n_lists, n_items


def _same_file(a, b):
    a, b = Path(a), Path(b)
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def cmd_backup(a, db):
    """Consistent copy via the SQLite backup API (safe while the DB is open elsewhere)."""
    db = Path(db)
    dest = Path(a.dest).expanduser().resolve()
    if not db.is_file():
        sys.exit(f"DB not found: {db} (nothing to back up)")
    if _same_file(db, dest) or dest == db:
        sys.exit("Backup destination is the source database itself.")
    if dest.exists() and not a.force:
        sys.exit(f"Destination exists: {dest}. Refusing to overwrite; pass --force to replace it.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    src = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        out = sqlite3.connect(tmp)
        try:
            src.backup(out)
        finally:
            out.close()
    except BaseException:
        src.close()
        if tmp.exists():
            tmp.unlink()
        raise
    src.close()
    try:
        n_lists, n_items = _check_db_file(tmp, "Backup")  # verify before it replaces anything
    except SystemExit:
        if tmp.exists():
            tmp.unlink()
        raise
    os.replace(tmp, dest)  # only now does the destination change
    print(f"Backup written: {dest} ({n_lists} list(s), {n_items} item(s))")


def cmd_restore(a, db):
    """Replace the configured DB with a validated backup (keeps a safety copy of the current DB)."""
    db = Path(db)
    srcp = Path(a.source).expanduser().resolve()
    if _same_file(srcp, db) or srcp == db:
        sys.exit("Restore source is the target database itself.")
    n_lists, n_items = _check_db_file(srcp, "Restore source")  # validate BEFORE touching the target
    safety = None
    if db.exists():
        if not a.force:
            sys.exit(f"Target DB exists: {db}. Refusing to overwrite; pass --force "
                     f"(the current DB is first saved as <db>.pre-restore-<timestamp>.bak).")
        safety = db.with_name(f"{db.name}.pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak")
        cur = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            bak = sqlite3.connect(safety)
            try:
                cur.backup(bak)
            finally:
                bak.close()
        finally:
            cur.close()
    db.parent.mkdir(parents=True, exist_ok=True)
    # Copy INTO the target through the backup API (one atomic write transaction), not by swapping files,
    # so a reader/writer holding the DB open never sees a half-written file.
    src = sqlite3.connect(f"file:{srcp.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(db)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    connect(db).close()  # apply additive schema migrations to an older backup
    print(f"Restored {db} from {srcp} ({n_lists} list(s), {n_items} item(s))")
    if safety:
        print(f"Previous DB saved as: {safety}")


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", help="DB file path (default: <repo root>/.ai/lists.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def mk(name, fn, help_, list_=True, number=False):
        s = sub.add_parser(name, help=help_)
        s.set_defaults(fn=fn)
        if list_:
            s.add_argument("list", help="list name, e.g. todo")
        if number:
            s.add_argument("number", type=int, help="item number")
        return s

    mk("path", cmd_path, "print resolved DB path", list_=False)
    mk("init", cmd_init, "create DB if missing", list_=False)
    s = mk("add", cmd_add, "add item (auto-creates list)")
    s.add_argument("title")
    s.add_argument("--priority")
    s.add_argument("--location")
    s.add_argument("--note")
    s.add_argument("--extra", help="free-form / JSON text")
    s.add_argument("--number", type=int, help="explicit number (default: max+1)")
    s.add_argument("--list-desc", help="description used if the list is created")
    s.add_argument("--set", action="append", metavar="FIELD=VALUE", help="custom field value (repeatable)")
    s.add_argument("--auto-field", action="store_true", help="auto-define unknown --set fields as text")
    s = mk("list", cmd_list, "list items ordered by number")
    s.add_argument("--status", choices=["open", "done", "all"], default="open")
    s.add_argument("--priority")
    s.add_argument("--json", action="store_true")
    mk("lists", cmd_lists, "list all lists", list_=False)
    mk("show", cmd_show, "show one item", number=True)
    s = mk("update", cmd_update, "update fields", number=True)
    for f in ("title", "priority", "location", "note", "extra"):
        s.add_argument("--" + f)
    s.add_argument("--set", action="append", metavar="FIELD=VALUE", help="set custom field (repeatable)")
    s.add_argument("--unset", action="append", metavar="FIELD", help="clear custom field (repeatable)")
    s.add_argument("--auto-field", action="store_true", help="auto-define unknown --set fields as text")
    mk("done", cmd_done, "mark done", number=True)
    mk("reopen", cmd_reopen, "mark open", number=True)
    s = mk("remove", cmd_remove, "delete item (number gap kept unless --renumber)", number=True)
    s.add_argument("--renumber", action="store_true")
    s = mk("move", cmd_move, "move item to position N, shifting others", number=True)
    s.add_argument("--to", type=int, required=True)
    mk("renumber", cmd_renumber, "compact numbers to 1..n keeping order")
    s = mk("field-add", cmd_field_add, "define a custom field for a list")
    s.add_argument("name")
    s.add_argument("--type", choices=FIELD_TYPES, default="text")
    s.add_argument("--desc")
    mk("field-list", cmd_field_list, "list a list's custom fields")
    s = mk("field-update", cmd_field_update, "rename / re-describe a field (type only if unused)")
    s.add_argument("name")
    s.add_argument("--rename")
    s.add_argument("--desc")
    s.add_argument("--type", choices=FIELD_TYPES)
    s = mk("field-remove", cmd_field_remove, "delete a field and all its values")
    s.add_argument("name")
    mk("drop-list", cmd_drop_list, "delete a whole list")
    s = mk("backup", cmd_backup, "write a consistent backup of the DB to DEST", list_=False)
    s.add_argument("dest", help="backup file path")
    s.add_argument("--force", action="store_true", help="overwrite DEST if it exists")
    s = mk("restore", cmd_restore, "replace the DB with a validated backup file", list_=False)
    s.add_argument("source", help="backup file to restore from")
    s.add_argument("--force", action="store_true", help="overwrite the existing DB (a .pre-restore-*.bak copy is kept)")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.fn(a, resolve_db(a.db))


if __name__ == "__main__":
    main()
