"""A stand-in for Streamlit good enough to RENDER a tab and see it run.

Why this exists: view_week() is several hundred lines of branching layout. The
unit tests cover what db.py returns, but nothing was executing the view itself,
so a typo in a branch that only fires when (say) a sitting is already logged
would reach the browser unnoticed.

This fake answers every widget with a plausible value instead of drawing
anything: selectboxes return their first option, checkboxes and buttons return
False, text inputs return their default. Nothing is clicked, so a render is
read-only — no write path fires — which is exactly what a smoke test wants.

Widgets record what they were asked to draw in `st.log`, so a test can assert a
tab actually rendered the thing it was supposed to.
"""
import contextlib
import datetime as dt
import types


class SessionState(dict):
    """st.session_state: dict access, attribute access, and `in`."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v

    def __delattr__(self, k):
        self.pop(k, None)


class Rerun(Exception):
    """Raised by st.rerun(), as Streamlit does, to stop the script."""


class _Ctx:
    """A column / form / expander / popover. Usable as a context manager
    (`with col:`) and directly (`col.metric(...)`), as Streamlit's are — calls
    made on it are delegated to the module."""

    def __init__(self, st=None):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = SessionState()
        self.log = []
        self.secrets = {}
        self.sidebar = _Ctx(self)

    # ---- layout ----------------------------------------------------------
    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx(self) for _ in range(n)]

    def tabs(self, labels, **kw):
        return [_Ctx(self) for _ in labels]

    def form(self, *a, **kw):
        return _Ctx(self)

    def expander(self, *a, **kw):
        return _Ctx(self)

    def popover(self, *a, **kw):
        return _Ctx(self)

    def container(self, *a, **kw):
        return _Ctx(self)

    def empty(self, *a, **kw):
        return _Ctx(self)

    # ---- output ----------------------------------------------------------
    def markdown(self, body="", **kw):
        self.log.append(("markdown", str(body)))

    def caption(self, body="", **kw):
        self.log.append(("caption", str(body)))

    def write(self, *a, **kw):
        self.log.append(("write", " ".join(str(x) for x in a)))

    def error(self, body="", **kw):
        self.log.append(("error", str(body)))

    def metric(self, label, value=None, **kw):
        self.log.append(("metric", f"{label}={value}"))

    def plotly_chart(self, *a, **kw):
        self.log.append(("chart", ""))

    # ---- input: never clicked, always answers with the default -----------
    def button(self, label="", **kw):
        self.log.append(("button", str(label)))
        return False

    def form_submit_button(self, label="", **kw):
        self.log.append(("submit", str(label)))
        return False

    def checkbox(self, label="", value=False, **kw):
        self.log.append(("checkbox", str(label)))
        return bool(value)

    def selectbox(self, label, options, index=0, format_func=None, **kw):
        opts = list(options)
        self.log.append(("selectbox", str(label)))
        if not opts:
            return None
        chosen = opts[index if 0 <= index < len(opts) else 0]
        if format_func:
            format_func(chosen)          # run it: it is real app code
        return chosen

    def radio(self, label, options, index=0, **kw):
        opts = list(options)
        self.log.append(("radio", str(label)))
        return opts[index] if opts else None

    def text_input(self, label="", value="", **kw):
        return value or ""

    def text_area(self, label="", value="", **kw):
        return value or ""

    def number_input(self, label="", value=0, **kw):
        return value

    def date_input(self, label="", value=None, **kw):
        return value or dt.date.today()

    def time_input(self, label="", value=None, **kw):
        return value or dt.time(9, 0)

    def slider(self, label="", min_value=0, **kw):
        return min_value

    def multiselect(self, label="", options=(), default=None, **kw):
        return list(default or [])

    def progress(self, *a, **kw):
        return _Ctx(self)

    # ---- control flow ----------------------------------------------------
    def rerun(self):
        raise Rerun()

    def stop(self):
        raise Rerun()

    def set_page_config(self, *a, **kw):
        pass

    def __getattr__(self, name):
        """Anything not modelled above is a no-op that records the call, so a
        newly used Streamlit API never crashes the smoke test spuriously."""
        def _noop(*a, **kw):
            self.log.append((name, ""))
            return None
        return _noop


class _CacheData:
    """@st.cache_data in both bare and parameterised forms, caching disabled."""

    def __call__(self, *args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return lambda fn: fn

    def clear(self):
        pass


def install():
    """Register the fake as `streamlit` (plus the stubs tracker.py imports)
    and return it. Call BEFORE importing tracker."""
    import sys
    st = FakeStreamlit()
    st.cache_data = _CacheData()
    st.cache_resource = _CacheData()
    sys.modules["streamlit"] = st

    supabase = types.ModuleType("supabase")
    supabase.create_client = lambda *a, **k: None
    supabase.Client = object
    sys.modules["supabase"] = supabase

    # plotly, used by the Week tab's category charts
    go = types.ModuleType("plotly.graph_objects")

    class _Fig:
        def __init__(self, *a, **kw):
            pass

        def update_layout(self, *a, **kw):
            return self

        def add_trace(self, *a, **kw):
            return self

        def add_shape(self, *a, **kw):
            return self

        def add_annotation(self, *a, **kw):
            return self

        def update_xaxes(self, *a, **kw):
            return self

        def update_yaxes(self, *a, **kw):
            return self

    go.Figure = _Fig
    for name in ("Bar", "Scatter", "Scattergl", "Heatmap"):
        setattr(go, name, lambda *a, **kw: None)
    plotly = types.ModuleType("plotly")
    plotly.graph_objects = go
    sys.modules["plotly"] = plotly
    sys.modules["plotly.graph_objects"] = go

    sls = types.ModuleType("streamlit_local_storage")
    sls.LocalStorage = lambda *a, **kw: types.SimpleNamespace(
        getItem=lambda *a, **k: None, setItem=lambda *a, **k: None,
        deleteItem=lambda *a, **k: None)
    sys.modules["streamlit_local_storage"] = sls
    return st


@contextlib.contextmanager
def rendering():
    """Swallow the Rerun a view may raise, so a test can assert on st.log."""
    try:
        yield
    except Rerun:
        pass
