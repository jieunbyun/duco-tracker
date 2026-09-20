"""Ordering the "Not yet planned" list by typing a position.

The board used to offer up/down arrows, which swapped two neighbours per
click. It now takes a number, so one move can jump an item past many others —
and the renumbering has to hold two things true that a swap got for free:

  * the PLANNED to-dos, which share one global sort_order with the listed
    ones but are drawn on the calendar rather than in this list, must not be
    dragged around by a move made in the list;
  * a move to the position an item already holds must write nothing, because
    the field is read on every rerun, not only when it is typed into.

Run it directly (no pytest needed):
    python tests/test_todo_reorder.py
Or, if you have pytest:
    pytest tests/test_todo_reorder.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_streamlit  # noqa: E402

st = fake_streamlit.install()

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import tracker  # noqa: E402

move = tracker.todo_order_after_move


def board(*ids):
    """A global to-do list already numbered 0..n-1, as the board keeps it."""
    return [{"id": i, "sort_order": n} for n, i in enumerate(ids)]


def applied(todos, moves):
    """The ids in the order the board would draw them after `moves`."""
    order = {t["id"]: moves.get(t["id"], t["sort_order"]) for t in todos}
    return [i for i, _ in sorted(order.items(), key=lambda kv: kv[1])]


def test_moving_an_item_to_the_top():
    todos = board("a", "b", "c", "d")
    moves = move(todos, ["a", "b", "c", "d"], "d", 1)
    assert applied(todos, moves) == ["d", "a", "b", "c"], moves


def test_moving_an_item_to_the_bottom():
    todos = board("a", "b", "c", "d")
    moves = move(todos, ["a", "b", "c", "d"], "a", 4)
    assert applied(todos, moves) == ["b", "c", "d", "a"], moves


def test_moving_into_the_middle():
    todos = board("a", "b", "c", "d", "e")
    moves = move(todos, ["a", "b", "c", "d", "e"], "e", 3)
    assert applied(todos, moves) == ["a", "b", "e", "c", "d"], moves


def test_asking_for_the_position_it_already_holds_writes_nothing():
    todos = board("a", "b", "c")
    assert move(todos, ["a", "b", "c"], "b", 2) == {}


def test_a_number_past_the_end_lands_at_the_end():
    todos = board("a", "b", "c")
    moves = move(todos, ["a", "b", "c"], "a", 99)
    assert applied(todos, moves) == ["b", "c", "a"], moves


def test_a_number_below_one_lands_at_the_top():
    todos = board("a", "b", "c")
    moves = move(todos, ["a", "b", "c"], "c", 0)
    assert applied(todos, moves) == ["c", "a", "b"], moves


def test_planned_todos_keep_their_place():
    """"p" is planned, so it is not in the list; a move among the listed
    items must not shuffle it past them."""
    todos = board("a", "p", "b", "c")
    moves = move(todos, ["a", "b", "c"], "c", 1)
    assert applied(todos, moves) == ["c", "p", "a", "b"], moves
    assert "p" not in moves, "a planned to-do was rewritten by a list move"


def test_unnumbered_todos_get_numbered():
    """A brand-new to-do arrives with a null sort_order; the first move has
    to give it one rather than leave it pinned to the bottom."""
    todos = [{"id": "a", "sort_order": None},
             {"id": "b", "sort_order": None}]
    moves = move(todos, ["a", "b"], "b", 1)
    assert moves == {"b": 0, "a": 1}, moves


def test_a_todo_that_is_not_on_the_board_is_ignored():
    todos = board("a", "b")
    assert move(todos, ["a", "b"], "gone", 1) == {}


# ---- plain-python runner (so `python tests/...` works without pytest) -----
if __name__ == "__main__":
    import traceback
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
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
