import io
import os
import traceback

import streamlit as st

from notebook_imports import state, Code, Editor

st.set_page_config(page_title="Mini notebook", layout="wide")

# -------------------------------------------------------------------
# Configurable editor heights
# -------------------------------------------------------------------

# Visible lines for the CODE editor before scrolling
max_lines = 20

# Visible lines for the MARKDOWN editor before scrolling
max_lines_markdown = 25

# -------------------------------------------------------------------
# Autosave configuration
# -------------------------------------------------------------------

# Turn autosave on/off
ENABLE_AUTOSAVE = True

# Load from autosave files on first use (per session)
AUTOLOAD_ON_START = True

# Where to store the last code / markdown on disk (relative to cwd)
CODE_AUTOSAVE_PATH = ".mini_notebook_code.py"
MARKDOWN_AUTOSAVE_PATH = ".mini_notebook_notes.md"

# Optional markdown->HTML converter for nicer, scrollable preview
try:
    import markdown as _md_lib

    def _md_to_html(text: str) -> str:
        return _md_lib.markdown(text, extensions=["fenced_code", "tables"])
except Exception:  # optional dependency
    _md_lib = None
    _md_to_html = None


# -------------------------------------------------------------------
# Autosave helpers
# -------------------------------------------------------------------

def _autosave(path: str, text: str) -> None:
    """Save text to a file, if autosave is enabled."""
    if not ENABLE_AUTOSAVE or not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        # Non-fatal; just let the user know
        try:
            st.toast(f"Autosave failed: {e}", icon="⚠️")
        except Exception:
            st.warning(f"Autosave failed: {e}")


def _autoload_if_needed(path: str, default_text: str) -> str:
    """
    Return initial text for a Code object.

    If AUTOLOAD_ON_START is True and the file exists, load it.
    Otherwise, fall back to default_text.
    """
    if AUTOLOAD_ON_START and path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            # If anything goes wrong, just use the default
            return default_text
    return default_text


# -------------------------------------------------------------------
# Code mode helpers
# -------------------------------------------------------------------

def _ensure_code_state():
    """Initialize session_state entries for code mode."""
    if "mini_code_code" not in state:
        initial = _autoload_if_needed(
            CODE_AUTOSAVE_PATH,
            "print('Hello from mini notebook!')",
        )
        state.mini_code_code = Code(initial)

    if "mini_code_ns" not in state:
        # Persistent namespace across runs
        state.mini_code_ns = {}

    if "mini_code_stdout" not in state:
        state.mini_code_stdout = ""
    if "mini_code_stderr" not in state:
        state.mini_code_stderr = ""
    if "mini_code_exception" not in state:
        state.mini_code_exception = ""


def _run_code():
    """Execute the current code in a persistent namespace and capture output."""
    code_obj: Code = state.mini_code_code
    src = code_obj.get_value()
    ns = state.mini_code_ns

    buf_out = io.StringIO()
    buf_err = io.StringIO()

    try:
        from contextlib import redirect_stdout, redirect_stderr

        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            exec(compile(src, "<mini_notebook_cell>", "exec"), ns)
        state.mini_code_exception = ""
    except Exception:
        state.mini_code_exception = traceback.format_exc()

    state.mini_code_stdout = buf_out.getvalue()
    state.mini_code_stderr = buf_err.getvalue()

    # Autosave current code source
    _autosave(CODE_AUTOSAVE_PATH, src)


def show_code_mode():
    st.title("Mini notebook – Code cell")

    _ensure_code_state()
    code_obj: Code = state.mini_code_code

    editor = Editor(
        code=code_obj,
        key="mini_code_editor",
        lang="python",
        min_lines=max_lines,
        max_lines=max_lines,
    )
    editor.show()

    # Run when clicking the button or pressing Ctrl+Enter
    if editor.event in ("run", "submit"):
        _run_code()

    # --- Output area below the editor ---
    if state.mini_code_stdout or state.mini_code_stderr or state.mini_code_exception:
        st.markdown("#### Output")

        if state.mini_code_stdout:
            st.code(state.mini_code_stdout, language="text")

        if state.mini_code_stderr:
            st.code(state.mini_code_stderr, language="text")

        if state.mini_code_exception:
            st.error(state.mini_code_exception)
    else:
        st.info("No output yet – write some code and press **Run** or **Ctrl+Enter**.")


# -------------------------------------------------------------------
# Markdown mode helpers
# -------------------------------------------------------------------

def _ensure_markdown_state():
    if "mini_md_code" not in state:
        initial = _autoload_if_needed(
            MARKDOWN_AUTOSAVE_PATH,
            "# Markdown notepad\n\nStart typing...",
        )
        state.mini_md_code = Code(initial)

    if "mini_md_last_run" not in state:
        # On first use, last_run = current text (implicitly "auto-run" for preview)
        state.mini_md_last_run = state.mini_md_code.get_value()


def show_markdown_mode():
    import streamlit.components.v1 as components

    st.title("Mini notebook – Markdown notepad")

    _ensure_markdown_state()
    code_obj: Code = state.mini_md_code

    col_editor, col_preview = st.columns(2)

    # ---- Left: editor ----
    with col_editor:
        editor = Editor(
            code=code_obj,
            key="mini_markdown_editor",
            lang="markdown",
            min_lines=max_lines_markdown,
            max_lines=max_lines_markdown,
        )
        editor.show()

        if editor.event in ("run", "submit"):
            state.mini_md_last_run = code_obj.get_value()
            # Autosave the last "confirmed" markdown
            _autosave(MARKDOWN_AUTOSAVE_PATH, state.mini_md_last_run)

        st.caption("Press **Run** or **Ctrl+Enter** to update the preview.")

    # ---- Right: compiled markdown preview in a scrollable box ----
    with col_preview:
        text = state.mini_md_last_run

        # Approximate height to match the editor "lines"
        line_height_px = 24
        lines = max_lines_markdown or 15
        preview_height = lines * line_height_px

        if _md_to_html is not None:
            html = _md_to_html(text)
            components.html(
                f"""
                <div style="
                    max-height: {preview_height}px;
                    overflow-y: auto;
                    padding: 0.5rem;
                ">
                    {html}
                </div>
                """,
                height=preview_height + 40,
                scrolling=False,
            )
        else:
            # Fallback if python-markdown isn't installed:
            # we still show the markdown, but Streamlit controls the height.
            st.warning(
                "Optional dependency `markdown` is not installed – "
                "preview will grow with content instead of scrolling.\n\n"
                "Install it with: `pip install markdown` to enable the scroll box."
            )
            st.markdown(text)


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------

def main():
    # Single, self-contained source of truth for the mode
    choice = st.sidebar.radio(
        "Notebook mode",                   # label
        ("Code cell", "Markdown notepad"), # options
        key="mini_notebook_mode",          # unique key so it won't clash
    )

    if choice == "Code cell":
        show_code_mode()
    else:
        show_markdown_mode()


if __name__ == "__main__":
    main()
