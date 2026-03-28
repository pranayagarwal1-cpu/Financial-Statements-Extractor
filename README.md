# Financial Statements Extractor 📊

An AI-powered pipeline that extracts balance sheets from financial PDF documents using a two-agent architecture: an Extraction Agent that pulls structured data from PDFs and an Evaluation Agent that validates output quality.

## 🌟 Features

- **Streamlit UI**: Upload PDFs, run extraction, and preview results in a browser
- **Intelligent Page Detection**: Claude AI identifies which pages contain balance sheets
- **High-Accuracy Extraction**: Landing AI ADE for precise table extraction with proper `colspan` handling
- **Structure Preservation**: `pd.read_html()` parses HTML tables natively, preserving column headers
- **Excel Export**: Saves extracted data to Excel in `output_excel/`
- **Visual Debugging**: Annotated images showing ADE-detected chunk boundaries
- **Cost Optimization**: Only balance sheet pages are sent to ADE (not entire documents)
- **Two-Agent Collaboration**: Extraction and Evaluation agents collaborate via a JSON manifest handoff

## 🏗️ Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (app.py)                       │
│         Upload PDFs → Run Extraction → Review → Download          │
└───────────────────────────────────────────────────────────────────┘
                                │
               ┌────────────────┴────────────────┐
               ▼                                 ▼
┌──────────────────────────┐       ┌──────────────────────────┐
│   Extraction Agent       │  ───▶ │   Evaluation Agent       │
│   (AI Agent.py)          │  JSON │   (Evaluation Agent.py)  │
│   LangChain + Claude     │manifest LangChain + Claude       │
└──────────────────────────┘       └──────────────────────────┘
         │                                    │
         ▼                                    ▼
┌──────────────┐  ┌──────────────┐   ┌──────────────────────┐
│ PDF Analysis │  │ ADE Extract  │   │  Quality Validation  │
│  (PyMuPDF)   │  │ (Landing AI) │   │  (Accounting Eq.)    │
└──────────────┘  └──────────────┘   └──────────────────────┘
```

**Extraction workflow**:
1. Lists PDFs in `input_files/`
2. Reads all pages with PyMuPDF; LLM identifies balance sheet pages
3. Exports each balance sheet page as a single-page PDF to `intermediate_files/`
4. Sends each page to Landing AI ADE; parses returned HTML with `pd.read_html()`
5. Coalesces duplicate columns caused by `colspan` headers
6. Saves to Excel in `output_excel/`
7. Writes `output_excel/extraction_manifest.json` as handoff for the Evaluation Agent

**Evaluation workflow**:
1. Reads `extraction_manifest.json` to discover produced files
2. Inspects each Excel file's structure
3. Validates accounting equation (Assets = Liabilities + Equity, ±1% tolerance)
4. Scores completeness and data quality
5. Saves JSON + Markdown report to `output_excel/`

## 📋 Prerequisites

- Python 3.8+
- Anthropic API key (for Claude)
- Landing AI API key (for ADE)

## 🚀 Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/financial-statements-extractor.git
cd financial-statements-extractor
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure API keys**
```bash
cp .env.example .env
```

Edit `.env` and add your API keys:
```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
LANDINGAI_API_KEY=your_landingai_api_key_here
```

## 📖 Usage

### Option 1 — Streamlit UI (recommended)

```bash
streamlit run app.py
```

- **Sidebar**: Upload PDF files (saved to `input_files/`) or manage existing ones
- **Step 1**: Click **Run Extraction** to invoke the Extraction Agent
- **Step 2**: Review extracted balance sheets inline; download Excel files

### Option 2 — Sequential pipeline (CLI)

Runs Extraction then Evaluation back-to-back:

```bash
python pipeline.py
```

### Option 3 — Extraction Agent only (CLI)

```bash
python "AI Agent.py"
```

## 📁 Project Structure

```
financial-statements-extractor/
├── AI Agent.py              # Extraction agent — LangChain + Landing AI ADE
├── Evaluation Agent.py      # Evaluation agent — validates extracted Excel files
├── pipeline.py              # Sequential orchestrator: Extraction → Evaluation
├── app.py                   # Streamlit UI
├── requirements.txt         # Python dependencies
├── .env                     # API keys (not in git)
├── .env.example             # Template for API keys
├── README.md                # This file
├── input_files/             # Place source PDFs here
├── output_excel/            # Extracted Excel files + evaluation reports
│   └── extraction_manifest.json   # Agent handoff file (auto-generated)
├── intermediate_files/      # Single-page PDFs and annotated images (auto-generated)
└── venv/                    # Virtual environment (not in git)
```

### Key constants (in `AI Agent.py`)

```python
INPUT_FOLDER      = "input_files"       # Source PDFs
OUTPUT_FOLDER     = "output_excel"      # Excel output
INTERMEDIATE_FILES = "intermediate_files"  # Temp PDFs and debug images
ADE_MODEL         = "dpt-2-latest"      # Landing AI model
```

## 🛠️ How Table Extraction Works

ADE returns balance sheet tables as HTML. Date headers are often wrapped in `<td colspan="2">`, which causes duplicate column names when parsed naively.

The pipeline uses `pd.read_html()` (which handles `colspan` natively) and then coalesces any remaining duplicate columns:

```python
dfs = pd.read_html(StringIO(table_content))
df = dfs[0]
# Merge duplicate columns (e.g. "30 June 2025" and "30 June 2025.1")
coalesced = {}
for col in df.columns:
    base = re.sub(r'\.\d+$', '', str(col))
    if base not in coalesced:
        coalesced[base] = df[col].copy()
    else:
        coalesced[base] = coalesced[base].combine_first(df[col])
df = pd.DataFrame(coalesced)
```

## 🤝 Agent Collaboration via Manifest

After extraction completes, `write_extraction_manifest()` writes:

```json
{
  "extraction_timestamp": "2026-03-27T...",
  "excel_files": [
    {
      "excel_path": "output_excel/Report_balance_sheet.xlsx",
      "source_pdf": "input_files/Report.pdf",
      "pages": [22]
    }
  ]
}
```

The Evaluation Agent reads this file as its starting point, so no paths are hard-coded between agents.

## 🔑 API Keys

### Anthropic API Key
1. Sign up at [console.anthropic.com](https://console.anthropic.com/)
2. Navigate to API Keys and create a new key
3. Add to `.env` as `ANTHROPIC_API_KEY`

### Landing AI API Key
1. Sign up at [app.landing.ai](https://app.landing.ai/)
2. Generate an ADE API key from your dashboard
3. Add to `.env` as `LANDINGAI_API_KEY`

## 💡 Tips & Best Practices

### Cost Optimization
- Only identified balance sheet pages are sent to ADE — not entire PDFs
- The agent checks ADE credits before starting and warns if low
- Use `intermediate_files/` to verify correct page identification before re-running

### Debugging
- Annotated PNGs in `intermediate_files/` show what ADE detected on each page
- Single-page PDFs in `intermediate_files/` let you verify page selection
- The Extraction log in the Streamlit UI captures full agent reasoning

### Common Issues

**Issue**: No balance sheets detected
- **Solution**: Confirm the PDF contains text-based tables (not scanned images); keywords like "Balance Sheet", "Assets", or "Liabilities" must appear in extracted text

**Issue**: ADE credit exhaustion
- **Solution**: Add credits to your Landing AI account; the agent checks automatically before processing

**Issue**: Misaligned columns in Excel
- **Solution**: Inspect annotated PNGs in `intermediate_files/` to verify ADE detected correct table boundaries

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Support for Income Statements and Cash Flow Statements
- Multi-language support
- Additional PDF layout formats
- Enhanced validation rules
- Automated accuracy testing suite

## 📄 License

MIT License — see LICENSE file for details.

## 🙏 Acknowledgments

- **LangChain**: Agent orchestration framework
- **Anthropic Claude**: LLM for page identification and reasoning
- **Landing AI ADE**: High-accuracy document table extraction
- **PyMuPDF**: PDF processing and manipulation
- **Pandas**: Data structuring and Excel export
- **Streamlit**: UI framework

---

**Status**: Active Development | **Version**: 2.0.0 | **Last Updated**: March 2026
