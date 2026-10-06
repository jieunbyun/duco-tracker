"""Every string in the app must be encodable as UTF-8.

An emoji written as two escaped halves ("\\ud83d\\udccc" rather than 📌) is
valid Python and renders fine against the fake Streamlit, but the real one
fails with UnicodeEncodeError the moment it sends the label to the browser.
This reads the source itself, so it catches such a string wherever it is,
whether or not any other test happens to render it.

Run it directly (no pytest needed):
    python tests/test_source_encoding.py
"""
import ast
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def unencodable_strings(path):
    """Line numbers of string literals in `path` that hold a lone surrogate."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and any(0xD800 <= ord(c) <= 0xDFFF for c in n.value)]


def test_every_string_in_the_app_encodes_as_utf8():
    for name in ("tracker.py", "db.py"):
        bad = unencodable_strings(os.path.join(REPO_ROOT, name))
        assert not bad, (
            f"{name} has strings Streamlit cannot send, at lines {bad}: "
            f"write the emoji itself, not its escaped surrogate halves")


if __name__ == "__main__":
    try:
        test_every_string_in_the_app_encodes_as_utf8()
        print("PASS  test_every_string_in_the_app_encodes_as_utf8")
    except AssertionError as exc:
        print(f"FAIL  {exc}")
        sys.exit(1)
