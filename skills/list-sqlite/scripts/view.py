#!/usr/bin/env python3
"""Read-only viewer: print a list ordered by list number.

  view.py                  # every list, open items
  view.py todo             # one list
  view.py todo --status all
  view.py --lists          # just names + counts
  view.py todo --json
DB: --db > env LIST_DB > <repo root>/.ai/lists.db
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lists as L


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("list", nargs="?", help="list name (default: all lists)")
    p.add_argument("--db")
    p.add_argument("--status", choices=["open", "done", "all"], default="open")
    p.add_argument("--priority")
    p.add_argument("--json", action="store_true")
    p.add_argument("--lists", action="store_true", help="show list names and counts only")
    a = p.parse_args()
    db = L.resolve_db(a.db)
    con = L.connect(db, readonly=True)
    if a.lists:
        L.cmd_lists(a, db)
        return
    rows = [L.get_list(con, a.list)] if a.list else con.execute("SELECT * FROM lists ORDER BY name").fetchall()
    out = []
    for lst in rows:
        r = L.print_list(con, lst, a.status, a.priority, a.json)
        if a.json:
            out += r
        else:
            print()
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
