# Usage Examples

Step-by-step examples for the Financial Statements Extractor pipeline.

## Table of Contents
- [Quick Start — Streamlit UI](#quick-start--streamlit-ui)
- [Quick Start — CLI](#quick-start--cli)
- [Understanding the Output](#understanding-the-output)
- [Advanced Usage](#advanced-usage)
- [Debugging and Troubleshooting](#debugging-and-troubleshooting)

---

## Quick Start — Streamlit UI

```bash
# Activate your virtual environment, then:
streamlit run app.py
```

1. **Sidebar** — drag-and-drop PDFs into the uploader; files are saved to `input_files/`
2. **Step 1** — click **Run Extraction**; a spinner shows agent progress
3. **Step 2** — review each balance sheet inline as a dataframe; download Excel files

---

## Quick Start — CLI

### Option A: Full pipeline (Extraction + Evaluation)

```bash
python pipeline.py
```

### Option B: Extraction only

```bash
python "AI Agent.py"
```

Place PDF files in `input_files/` before running.

### Expected console output (extraction)

```
======================================================================
🤖 BALANCE SHEET EXTRACTION AGENT
======================================================================

--- Iteration 1 ---
🔧 Tool: check_ade_credits
📤 Output: {"status": "success", "message": "Landing AI ADE is accessible"}

--- Iteration 2 ---
🔧 Tool: list_pdf_files_in_folder
📥 Args: {"folder_path": "input_files"}
📤 Output: {"status": "success", "count": 1, "files": ["FinancialReport.pdf"]}

--- Iteration 3 ---
🔧 Tool: extract_text_from_pdf_pages
📤 Output: {"status": "success", "total_pages": 45, "pages": [...]}

--- Iteration 4 ---
🔧 Tool: identify_balance_sheet_pages
📤 Output: {"status": "success", "pages": [22], "confidence": "high"}

--- Iteration 5 ---
🔧 Tool: extract_balance_sheet_with_ade
      → Saved temp PDF: intermediate_files/FinancialReport_page22_for_ADE.pdf
      → Saved annotated image: intermediate_files/FinancialReport_page22_for_ADE_annotated.png
      ✅ Extracted table with 45 rows on page 22
📤 Output: {"status": "success", "tables_found": 1}

--- Iteration 6 ---
🔧 Tool: parse_and_save_to_excel
📤 Output: {"status": "success", "output_file": "output_excel/FinancialReport_balance_sheet.xlsx"}

--- Iteration 7 ---
🔧 Tool: write_extraction_manifest
📤 Output: {"status": "success", "manifest_path": "output_excel/extraction_manifest.json"}

✅ Agent finished!
```

---

## Understanding the Output

### Generated files

```
output_excel/
├── FinancialReport_balance_sheet.xlsx     ← Extracted balance sheet
└── extraction_manifest.json               ← Handoff file for Evaluation Agent

intermediate_files/
├── FinancialReport_page22_for_ADE.pdf     ← Single-page PDF sent to ADE
└── FinancialReport_page22_for_ADE_annotated.png  ← Visual debugging
```

### Excel format

One sheet per balance sheet page (`Page22`, `Page23`, etc.):

```
| Description              | 30 June 2025 | 31 December 2024 |
|--------------------------|--------------|------------------|
| Assets                   |              |                  |
| Non-current assets       |              |                  |
| Property, plant & equip  | 8,456        | 8,234            |
| Intangible assets        | 234          | 245              |
| ...                      | ...          | ...              |
```

Headers are extracted using `pd.read_html()`, which correctly handles `colspan` attributes in ADE's HTML output. Duplicate column names (e.g. `30 June 2025` and `30 June 2025.1`) are coalesced automatically.

### Annotated images

The PNG files overlay ADE's detected chunks on the page:
- **Blue boxes** — table chunks
- **Green boxes** — text chunks
- **Purple boxes** — marginalia

---

## Advanced Usage

### Process a single PDF with specific pages

Edit the task at the bottom of `AI Agent.py`:

```python
if __name__ == "__main__":
    task = """
    Process only Q4-2024-Report.pdf.
    Extract balance sheet from pages 18-20 only.
    """
    result = run_agent(task, max_iterations=15)
```

### Use ADE.py directly (no agent)

If you know exact page numbers and want to skip LLM page detection:

```bash
python ADE.py
```

Edit `ADE.py` to specify the PDF filename and page numbers before running.

### Batch processing via script

```python
import importlib.util, sys, os

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

agent = load_module("ai_agent", "AI Agent.py")

for pdf in ["CompanyA.pdf", "CompanyB.pdf"]:
    task = f"Extract balance sheet from input_files/{pdf}"
    agent.run_agent(task, max_iterations=15)
```

---

## Debugging and Troubleshooting

### Strategy 1: Visual inspection

Open the annotated PNG in `intermediate_files/`:
- Blue boxes should cover the balance sheet table
- If boxes are wrong → ADE detection issue
- If boxes are correct but numbers are wrong → parsing issue

### Strategy 2: Console output

```
✅ Confirmed as Balance Sheet table    ← Good
⏭️  Table doesn't match criteria       ← Wrong table detected
❌ Failed to parse table data          ← Parsing problem
```

### Strategy 3: Inspect intermediate PDFs

Open single-page PDFs in `intermediate_files/` to confirm:
- Correct page was extracted
- Text is selectable (not a scanned image)
- Table is clearly visible

---

### Common issues

#### No balance sheets detected

```json
{"status": "no_balance_sheet", "pages": []}
```

- Confirm the PDF is text-based: press Ctrl+F in a PDF viewer and search for "Assets"
- If scanned, run OCR first
- Manually specify pages in the task prompt

#### ADE credits exhausted

```json
{"status": "insufficient_credits"}
```

- Add credits in your Landing AI dashboard
- Re-run; the agent checks credits at the start

#### Misaligned columns in Excel

- Open the annotated PNG — did ADE draw boxes over the correct table area?
- If boundaries look correct, the table may have an unusual nested header structure; inspect the raw HTML returned by ADE in the console output

#### Processing takes too long

- Set `max_iterations` lower (default 25)
- Reduce `max_pages` in `extract_text_from_pdf_pages` if you know the balance sheet is near the front
- Specify exact page numbers in the task prompt to skip LLM detection

---

## Full workflow example

```bash
# 1. Activate environment
source venv/bin/activate

# 2. Copy PDFs to input folder
cp ~/Downloads/FinancialReport.pdf input_files/

# 3a. Run via Streamlit (browser UI)
streamlit run app.py

# --- OR ---

# 3b. Run via CLI (extraction + evaluation)
python pipeline.py

# --- OR ---

# 3c. Run extraction only
python "AI Agent.py"

# 4. Open results
open output_excel/FinancialReport_balance_sheet.xlsx

# 5. Debug if needed
open intermediate_files/FinancialReport_page22_for_ADE_annotated.png
```

---

See [EVALUATION_FRAMEWORK.md](EVALUATION_FRAMEWORK.md) for KPIs, accuracy targets, and evaluation methodology.
