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
"""


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


def fmt_item(r):
    box = "[x]" if r["status"] == "done" else "[ ]"
    pri = f" [{r['priority']}]" if r["priority"] else ""
    s = f"{r['number']:>3}. {box}{pri} {r['title']}"
    if r["location"]:
        s += f"  ({r['location']})"
    if r["note"]:
        s += "\n       " + r["note"].replace("\n", "\n       ")
    return s


def print_list(con, lst, status="open", priority=None, as_json=False):
    rows = fetch_items(con, lst, status, priority)
    if as_json:
        return [{"list": lst["name"], **{k: r[k] for k in r.keys() if k not in ("id", "list_id")}} for r in rows]
    print(f"# {lst['name']}" + (f" - {lst['description']}" if lst["description"] else ""))
    if not rows:
        print("(empty)")
    for r in rows:
        print(fmt_item(r))
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


def cmd_update(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        r = get_item(con, lst, a.number)
        sets = {k: v for k, v in (("title", a.title), ("priority", a.priority), ("location", a.location),
                                   ("note", a.note), ("extra", a.extra)) if v is not None}
        if not sets:
            sys.exit("Nothing to update.")
        sets["updated_at"] = now()
        con.execute(f"UPDATE items SET {','.join(k + '=?' for k in sets)} WHERE id=?", [*sets.values(), r["id"]])
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


def cmd_drop_list(a, db):
    con = connect(db)
    with con:
        lst = get_list(con, a.list)
        con.execute("DELETE FROM lists WHERE id=?", (lst["id"],))
    print(f"Dropped list {a.list}")


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
    s = mk("list", cmd_list, "list items ordered by number")
    s.add_argument("--status", choices=["open", "done", "all"], default="open")
    s.add_argument("--priority")
    s.add_argument("--json", action="store_true")
    mk("lists", cmd_lists, "list all lists", list_=False)
    mk("show", cmd_show, "show one item", number=True)
    s = mk("update", cmd_update, "update fields", number=True)
    for f in ("title", "priority", "location", "note", "extra"):
        s.add_argument("--" + f)
    mk("done", cmd_done, "mark done", number=True)
    mk("reopen", cmd_reopen, "mark open", number=True)
    s = mk("remove", cmd_remove, "delete item (number gap kept unless --renumber)", number=True)
    s.add_argument("--renumber", action="store_true")
    s = mk("move", cmd_move, "move item to position N, shifting others", number=True)
    s.add_argument("--to", type=int, required=True)
    mk("renumber", cmd_renumber, "compact numbers to 1..n keeping order")
    mk("drop-list", cmd_drop_list, "delete a whole list")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.fn(a, resolve_db(a.db))


if __name__ == "__main__":
    main()
