"""In-memory stand-in for the Supabase client, so db.py can be tested without a
live backend.

Why this exists: db.py talks to Supabase through a fluent query builder
(`client().table(x).select(...).eq(...).execute().data`). The app's row scoping
is enforced in Python (see db._visible_project_ids), so we can exercise it fully
against fake tables — no network, no secrets, runnable on every change.

Usage:
    import fake_supabase
    db = fake_supabase.load_db()
    db.client = lambda: fake_supabase.FakeSupabase({"project": [...], ...})
    # ... monkeypatch db.my_app_user_id / db._uid to choose the current user ...
"""
import importlib.util
import os
import sys
import types


class _CacheData:
    """No-op replacement for st.cache_data: supports both @cache_data and
    @cache_data(ttl=...) forms, and a .clear() method. Caching is disabled in
    tests so each call re-reads the fake tables (no cross-user staleness)."""

    def __call__(self, *args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            return args[0]                      # bare @cache_data
        return lambda fn: fn                    # @cache_data(ttl=...)

    def clear(self):
        pass


def _install_stubs():
    """Register fake `streamlit` and `supabase` modules so `import db` works."""
    from unittest.mock import MagicMock
    st = MagicMock(name="streamlit")
    st.cache_data = _CacheData()               # must be real, not a MagicMock
    sys.modules["streamlit"] = st
    supabase = types.ModuleType("supabase")
    supabase.create_client = lambda *a, **k: None
    supabase.Client = object
    sys.modules["supabase"] = supabase


def load_db():
    """Install stubs and import the app's db.py fresh. Returns the module."""
    _install_stubs()
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "db", os.path.join(repo_root, "db.py"))
    db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(db)
    return db


class _Query:
    """Mimics the subset of the PostgREST builder db.py uses. Every filter
    returns a new _Query so calls can chain in any order, matching Supabase."""

    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *args, **kwargs):
        return self

    def _where(self, pred):
        return _Query([r for r in self.rows if pred(r)])

    def eq(self, col, val):
        return self._where(lambda r: r.get(col) == val)

    def neq(self, col, val):
        return self._where(lambda r: r.get(col) != val)

    def in_(self, col, vals):
        allowed = set(vals)
        return self._where(lambda r: r.get(col) in allowed)

    def gte(self, col, val):
        return self._where(lambda r: r.get(col) is not None and r.get(col) >= val)

    def lte(self, col, val):
        return self._where(lambda r: r.get(col) is not None and r.get(col) <= val)

    def lt(self, col, val):
        return self._where(lambda r: r.get(col) is not None and r.get(col) < val)

    def is_(self, col, val):
        if val in ("null", None):
            return self._where(lambda r: r.get(col) is None)
        return self._where(lambda r: r.get(col) == val)

    def order(self, *args, **kwargs):
        return self

    def limit(self, n):
        return _Query(self.rows[:n])

    def execute(self):
        return types.SimpleNamespace(data=[dict(r) for r in self.rows])


class FakeSupabase:
    """A fake client seeded with {table_name: [row dicts]}."""

    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables.get(name, []))
