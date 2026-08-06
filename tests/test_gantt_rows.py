"""Regression tests for which projects get a row on the Gantt.

Every row costs a fixed slice of chart height (110 + 46*n) whether or not
anything is drawn in it. The chart's x-axis is pinned to a 12-month window, so
a project whose dates fall entirely outside that window draws nothing — and
before gantt_rows() existed it still held a lane, producing tall bands of blank
chart with no bars and no labels. These tests keep rows and drawn bars in sync.

tracker.py imports streamlit and plotly at module scope, so this parses the two
pure helpers out of the source and executes just those, keeping the test free
of the app's dependencies (the same reason db.py is loaded via a stub in
fake_supabase.py).

Run it directly (no pytest needed):
    python tests/test_gantt_rows.py
Or, if you have pytest:
    pytest tests/test_gantt_rows.py
"""
import ast
import datetime as dt
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WANTED = ("gantt_window_end", "gantt_rows")


def _load_helpers():
    """Exec just the named top-level functions from tracker.py."""
    path = os.path.join(REPO_ROOT, "tracker.py")
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    picked = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name in WANTED]
    missing = set(WANTED) - {n.name for n in picked}
    assert not missing, f"tracker.py no longer defines {sorted(missing)}"
    ns = {"dt": dt}
    exec(compile(ast.Module(body=picked, type_ignores=[]), path, "exec"), ns)
    return ns


_ns = _load_helpers()
gantt_window_end = _ns["gantt_window_end"]
gantt_rows = _ns["gantt_rows"]

WIN_START = dt.date(2026, 8, 1)
WIN_END = gantt_window_end(WIN_START)          # 1 Aug 2027


def proj(name, started_on, due_on):
    return {"name": name, "started_on": started_on, "due_on": due_on}


CURRENT = proj("Current", "2026-09-01", "2027-02-01")     # inside
FINISHED = proj("Finished", "2023-01-01", "2024-06-01")   # ended long before
FUTURE = proj("Future", "2028-01-01", "2028-12-01")       # starts after
SPANNING = proj("Spanning", "2020-01-01", "2030-01-01")   # straddles it
UNDATED = {"name": "Undated", "started_on": None, "due_on": None}


def names(rows):
    return [p["name"] for p in rows]


def test_only_projects_overlapping_the_window_get_a_row():
    rows, offscreen, undated = gantt_rows(
        [CURRENT, FINISHED, FUTURE, SPANNING], WIN_START, WIN_END)
    assert names(rows) == ["Current", "Spanning"]
    assert names(offscreen) == ["Finished", "Future"]
    assert undated == []


def test_a_project_spanning_the_whole_window_is_drawn():
    """It has no endpoint inside the window; it must still get a row."""
    rows, _, _ = gantt_rows([SPANNING], WIN_START, WIN_END)
    assert names(rows) == ["Spanning"]


def test_projects_touching_the_very_edges_count_as_visible():
    starts_on_last_day = proj("Edge start", "2027-08-01", "2029-01-01")
    ends_on_first_day = proj("Edge end", "2020-01-01", "2026-08-01")
    rows, offscreen, _ = gantt_rows(
        [starts_on_last_day, ends_on_first_day], WIN_START, WIN_END)
    assert names(rows) == ["Edge start", "Edge end"]
    assert offscreen == []


def test_one_day_outside_the_edges_is_excluded():
    just_after = proj("Just after", "2027-08-02", "2029-01-01")
    just_before = proj("Just before", "2020-01-01", "2026-07-31")
    rows, offscreen, _ = gantt_rows(
        [just_after, just_before], WIN_START, WIN_END)
    assert rows == []
    assert names(offscreen) == ["Just after", "Just before"]


def test_undated_projects_are_separated_not_charted():
    rows, offscreen, undated = gantt_rows(
        [CURRENT, UNDATED], WIN_START, WIN_END)
    assert names(rows) == ["Current"]
    assert names(undated) == ["Undated"]
    assert offscreen == []


def test_order_is_preserved_so_the_lead_divider_stays_correct():
    """render_gantt draws its led/participant divider by counting i_lead rows
    from the front of the list, so filtering must not reorder anything."""
    ordered = [proj(f"P{i}", "2026-09-01", "2027-02-01") for i in range(4)]
    ordered.insert(2, FINISHED)                # drops out of the middle
    rows, _, _ = gantt_rows(ordered, WIN_START, WIN_END)
    assert names(rows) == ["P0", "P1", "P2", "P3"]


def test_every_row_would_actually_draw_inside_the_window():
    """The invariant behind the fix: no row is blank. Checked directly against
    the window rather than by re-running the filter."""
    rows, _, _ = gantt_rows(
        [CURRENT, FINISHED, FUTURE, SPANNING, UNDATED], WIN_START, WIN_END)
    for p in rows:
        s = dt.date.fromisoformat(p["started_on"])
        e = dt.date.fromisoformat(p["due_on"])
        assert s <= WIN_END and e >= WIN_START, (
            f'{p["name"]} got a row but draws nothing in the window')


def test_window_end_is_twelve_months_on():
    assert gantt_window_end(dt.date(2026, 8, 1)) == dt.date(2027, 8, 1)
    assert gantt_window_end(dt.date(2026, 3, 15)) == dt.date(2027, 3, 15)


def test_leap_day_window_does_not_crash():
    """29 Feb has no anniversary in a common year — it must fall forward."""
    assert gantt_window_end(dt.date(2028, 2, 29)) == dt.date(2029, 3, 1)


# ---- plain-python runner (so `python tests/...` works without pytest) -----
if __name__ == "__main__":
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
        except Exception:                       # noqa: BLE001
            failures += 1
            print(f"ERROR {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
