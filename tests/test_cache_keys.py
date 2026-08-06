"""Regression test for the cross-user cache leak.

st.cache_data is a SERVER-WIDE cache shared by every visitor. A cached function
that returns user-specific rows must therefore take the auth uid as a real
argument so each user gets their own entry.

Streamlit deliberately excludes arguments whose name starts with "_" from the
cache key (the escape hatch for unhashable values such as DB connections). So
writing `def _my_app_user(_u)` silently collapses every user onto ONE cache
entry: the first caller fills it and everyone else is served that person's
rows — including their identity — until the TTL expires. That is exactly the
bug this test exists to prevent, and it is invisible in single-user testing.

This is a source-level check (ast), not a runtime one, because the test suite
stubs caching out entirely — the mistake is in the decorator's key, so the
decorator's key is what we inspect.

Run it directly (no pytest needed):
    python tests/test_cache_keys.py
Or, if you have pytest:
    pytest tests/test_cache_keys.py
"""
import ast
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = ["db.py", "tracker.py"]


def _is_cache_data(dec):
    """True for @st.cache_data and @st.cache_data(ttl=...)."""
    node = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(node, ast.Attribute) and node.attr == "cache_data"


def cached_functions():
    """Yield (source file, FunctionDef) for every @st.cache_data function."""
    for name in SOURCES:
        path = os.path.join(REPO_ROOT, name)
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    any(_is_cache_data(d) for d in node.decorator_list):
                yield name, node


def _arg_names(fn):
    a = fn.args
    return [x.arg for x in (a.posonlyargs + a.args + a.kwonlyargs)]


def test_no_cached_function_has_an_underscore_argument():
    offenders = [f"{src}:{fn.lineno} {fn.name}({arg})"
                 for src, fn in cached_functions()
                 for arg in _arg_names(fn) if arg.startswith("_")]
    assert not offenders, (
        "Underscore-prefixed arguments are EXCLUDED from the st.cache_data "
        "key, so these functions share one cache entry across all users:\n  "
        + "\n  ".join(offenders)
        + "\nDrop the underscore so the value becomes part of the key.")


def test_the_check_actually_finds_cached_functions():
    """Guard against the test silently passing because it matched nothing
    (e.g. if the decorator is ever imported/aliased differently)."""
    found = list(cached_functions())
    assert len(found) > 5, f"only found {len(found)} cached functions"


def test_per_user_caches_take_the_uid_argument():
    """Every cached function whose public wrapper passes _uid() must still
    declare it. Cheap sanity check that the `u` convention is intact."""
    by_name = {fn.name: fn for _, fn in cached_functions()}
    for name in ("_my_app_user", "_my_projects", "_project_tracker"):
        assert name in by_name, f"{name} is no longer cached — check why"
        assert "u" in _arg_names(by_name[name]), (
            f"{name} lost its per-user cache key argument")


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
