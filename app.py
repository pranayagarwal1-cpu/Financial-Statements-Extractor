"""
Streamlit UI — Financial Statements Extractor Pipeline

Layout:
  Sidebar  — upload PDFs, manage input files
  Main     — Step 1: Extract  →  Step 2: Human review gate  →  Step 3: Evaluate + Report
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
INPUT_FOLDER    = BASE_DIR / "input_files"
OUTPUT_FOLDER   = BASE_DIR / "output_excel"
INTERMEDIATE    = BASE_DIR / "intermediate_files"
PYTHON          = str(BASE_DIR / "venv" / "bin" / "python")

for d in [INPUT_FOLDER, OUTPUT_FOLDER, INTERMEDIATE]:
    d.mkdir(exist_ok=True)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Financial Statements Extractor",
    page_icon="📊",
    layout="wide",
)

# ── Minimal custom styling ────────────────────────────────────────────────────
st.markdown("""
<style>
    /* tighter metric cards */
    [data-testid="metric-container"] { background: #f8f9fa; border-radius: 8px; padding: 12px; }
    /* step header pills */
    .step-pill {
        display: inline-block; padding: 2px 12px; border-radius: 12px;
        font-size: 0.75rem; font-weight: 600; margin-bottom: 4px;
    }
    .step-done  { background:#d4edda; color:#155724; }
    .step-active{ background:#cce5ff; color:#004085; }
    .step-wait  { background:#e2e3e5; color:#383d41; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
DEFAULTS = {
    "stage":          "upload",   # upload | extracted
    "extraction_log": "",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ───────────────────────────────────────────────────────────────────

def run_script(script_name: str):
    """Run a script with the venv Python; return (combined output, success)."""
    result = subprocess.run(
        [PYTHON, script_name],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
    )
    output = result.stdout
    if result.stderr:
        output += f"\n\n--- STDERR ---\n{result.stderr}"
    return output, result.returncode == 0


def get_excel_files():
    return sorted(OUTPUT_FOLDER.glob("*.xlsx"))



def load_excel(path: Path):
    xl = pd.ExcelFile(path)
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}


def step_pill(label: str, state: str) -> None:
    css = {"done": "step-done", "active": "step-active", "wait": "step-wait"}[state]
    st.markdown(f'<span class="step-pill {css}">{label}</span>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — file management
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("📊 FS Extractor")
    st.caption("Balance sheet extraction pipeline")
    st.divider()

    st.subheader("📁 Input PDFs")
    uploaded = st.file_uploader(
        "Drop PDF reports here",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded:
        saved = 0
        for f in uploaded:
            dest = INPUT_FOLDER / f.name
            dest.write_bytes(f.getvalue())
            saved += 1
        st.success(f"Saved {saved} file(s) to input_files/")

    st.divider()
    existing_pdfs = sorted(INPUT_FOLDER.glob("*.pdf"))
    if existing_pdfs:
        st.caption(f"{len(existing_pdfs)} file(s) ready:")
        for pdf in existing_pdfs:
            col_name, col_del = st.columns([4, 1])
            col_name.markdown(f"📄 `{pdf.name}`")
            if col_del.button("✕", key=f"del_{pdf.name}", help="Remove"):
                pdf.unlink()
                st.rerun()
        if st.button("🗑 Clear all", use_container_width=True):
            for pdf in existing_pdfs:
                pdf.unlink()
            st.rerun()
    else:
        st.info("No PDFs in input_files/ yet.")

    st.divider()

    # Quick output links
    st.subheader("📂 Output folders")
    st.caption(f"Extracted Excel → `output_excel/`")
    st.caption(f"Intermediate pages → `intermediate_files/`")

    # Reset pipeline
    st.divider()
    if st.button("↺ Reset pipeline", use_container_width=True):
        for key in DEFAULTS:
            st.session_state[key] = DEFAULTS[key]
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — pipeline steps
# ═══════════════════════════════════════════════════════════════════════════════
stage = st.session_state.stage

# ── Top status bar ─────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("PDFs ready",      len(existing_pdfs))
m2.metric("Excel files out", len(get_excel_files()))
m3.metric("Input folder",    "input_files/")
m4.metric("Output folder",   "output_excel/")

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════
pill_state = "done" if stage in ("extracted", "evaluated") else "active" if stage == "upload" else "wait"
step_pill("Step 1 — Extract Balance Sheets", pill_state)
st.subheader("Extract Balance Sheets")

if not existing_pdfs:
    st.warning("Upload at least one PDF in the sidebar to get started.")
else:
    col_btn, col_status = st.columns([2, 5])

    with col_btn:
        run_extract = st.button(
            "▶ Run Extraction",
            type="primary",
            use_container_width=True,
        )

    with col_status:
        if stage == "extracted":
            st.success(f"✅ Done — {len(get_excel_files())} Excel file(s) in output_excel/")

    if run_extract:
        # Clear previous outputs so we start fresh
        for f in OUTPUT_FOLDER.glob("*.xlsx"):
            f.unlink()
        st.session_state.stage = "upload"
        st.session_state.extraction_log = ""
        st.session_state.evaluation_log = ""

        with st.spinner("Extraction Agent running… this may take a minute."):
            log, ok = run_script("AI Agent.py")

        st.session_state.extraction_log = log
        st.session_state.stage = "extracted" if ok else "upload"
        if not ok:
            st.error("Extraction failed — check the log below.")
        st.rerun()

    if st.session_state.extraction_log:
        with st.expander("📋 Extraction log", expanded=False):
            st.code(st.session_state.extraction_log, language="")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — HUMAN REVIEW GATE
# ══════════════════════════════════════════════════════════════════════════════
if stage == "extracted":
    st.divider()
    step_pill("Step 2 — Review Extracted Data", "active")
    st.subheader("Review Extracted Data")
    st.caption("Inspect the extracted balance sheets below and download any files you need.")

    excel_files = get_excel_files()
    if not excel_files:
        st.warning("No Excel files found — try re-running extraction.")
    else:
        for xlsx in excel_files:
            with st.expander(f"📄 {xlsx.name}", expanded=True):
                sheets = load_excel(xlsx)
                for sheet_name, df in sheets.items():
                    st.caption(
                        f"Sheet: **{sheet_name}** · "
                        f"{len(df)} rows · {len(df.columns)} columns"
                    )
                    st.dataframe(
                        df.fillna(""),
                        use_container_width=True,
                        height=min(400, 40 + len(df) * 35),
                    )
                    st.download_button(
                        f"⬇ Download {xlsx.name}",
                        data=xlsx.read_bytes(),
                        file_name=xlsx.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{xlsx.name}",
                    )

        st.markdown("---")
        if st.button("🔄 Re-run Extraction", use_container_width=False):
            st.session_state.stage = "upload"
            st.session_state.extraction_log = ""
            st.rerun()
