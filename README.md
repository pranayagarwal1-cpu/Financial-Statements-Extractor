# Financial Statements Extractor 📊

An intelligent AI agent that automatically extracts balance sheets from financial PDF documents using LangChain orchestration and Landing AI's Agentic Document Extraction (ADE).

## 🌟 Features

- **Intelligent Page Detection**: Uses Claude AI to identify pages containing balance sheets
- **High-Accuracy Extraction**: Leverages Landing AI's ADE for precise table extraction
- **Structure Preservation**: Maintains hierarchical relationships and table structure
- **Excel Export**: Saves extracted data to Excel with proper formatting
- **Visual Debugging**: Generates annotated images showing detected chunks and bounding boxes
- **Cost Optimization**: Sends only identified balance sheet pages to ADE (not entire documents)
- **Automated Processing**: Batch processes multiple PDFs with minimal configuration

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     LangChain Agent                         │
│                   (Claude Sonnet 4.5)                       │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ PDF Analysis │   │ ADE Extract  │   │ Excel Export │
│  (PyMuPDF)   │   │ (Landing AI) │   │  (Pandas)    │
└──────────────┘   └──────────────┘   └──────────────┘
```

**Workflow**:
1. Agent lists PDF files in input folder
2. Extracts text from all pages using PyMuPDF
3. LLM identifies pages containing balance sheets
4. Extracts single-page PDFs for identified pages
5. Sends each page to Landing AI ADE for table extraction
6. Parses HTML tables to clean markdown format
7. Saves to Excel with structural integrity

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

### Basic Usage

Place your PDF files in the project directory and run:

```bash
python "AI Agent.py"
```

The agent will:
- Process all PDFs in the current folder
- Identify balance sheet pages automatically
- Extract tables and save to `output_excel/` folder
- Save temporary PDFs and annotated images to `temp_ade_pages/` for inspection

### Output Files

```
output_excel/
├── Alliander-Half-Year-Report-2025_balance_sheet.xlsx
└── [other extracted files]

temp_ade_pages/
├── Alliander-Half-Year-Report-2025_page22_for_ADE.pdf
├── Alliander-Half-Year-Report-2025_page22_for_ADE_annotated.png
└── [other temp files]
```

### Custom Configuration

Edit constants in `AI Agent.py`:

```python
INPUT_FOLDER = "."                    # Folder containing PDFs
OUTPUT_FOLDER = "output_excel"        # Excel output location
TEMP_ADE_FOLDER = "temp_ade_pages"    # Temp files for inspection
ADE_MODEL = "dpt-2-latest"            # Landing AI model
```

## 🛠️ Advanced Usage

### Using ADE.py Directly

For direct ADE processing without agent orchestration:

```bash
python ADE.py
```

### Custom Task

Modify the task in `AI Agent.py` main block:

```python
task = """
Process specific PDF: Alliander-Half-Year-Report-2025.pdf
Extract balance sheet from pages 20-25 only.
"""
result = run_agent(task, max_iterations=20)
```

## 📊 Features in Detail

### HTML to Markdown Conversion
- Intelligently handles `colspan` and `rowspan` attributes
- Preserves header structure across multiple columns
- Distinguishes between generic headers (€ million) and specific headers (dates)

### Structural Integrity
- **Multiline Cell Expansion**: Splits cells containing newlines into separate rows
- **Text/Number Splitting**: Separates merged text and numerical values
- **Header Detection**: Automatically identifies header rows
- **Column Alignment**: Ensures values align with correct headers

### Balance Sheet Validation
- Verifies presence of Assets, Liabilities, and Equity sections
- Validates against accounting rules (Assets = Liabilities + Equity)
- Filters out non-balance sheet tables automatically

## 🎯 Evaluation & KPIs

See [EVALUATION_FRAMEWORK.md](EVALUATION_FRAMEWORK.md) for:
- Key Performance Indicators (Accuracy, Completeness, Efficiency)
- OKRs for production readiness
- Benchmark targets and testing methodology
- Quick start evaluation guide

**Key Metrics**:
- Field-Level Accuracy: Target ≥95%
- Structural Accuracy: Target ≥90%
- Balance Validation: Target 100%
- Credit Efficiency: Target ≥85%

## 📁 Project Structure

```
financial-statements-extractor/
├── AI Agent.py              # Main LangChain orchestration agent
├── ADE.py                   # Direct ADE processing script
├── helper.py                # Utility functions
├── requirements.txt         # Python dependencies
├── .env                     # API keys (not in git)
├── .env.example             # Template for API keys
├── README.md                # This file
├── EVALUATION_FRAMEWORK.md  # KPIs and evaluation methodology
├── output_excel/            # Extracted Excel files
├── temp_ade_pages/          # Temporary PDFs and annotated images
└── venv/                    # Virtual environment (not in git)
```

## 🔑 API Keys

### Anthropic API Key
1. Sign up at [console.anthropic.com](https://console.anthropic.com/)
2. Navigate to API Keys section
3. Create new key and copy to `.env`

### Landing AI API Key
1. Sign up at [landingai.com](https://landingai.com/)
2. Access your account dashboard
3. Generate API key for ADE access
4. Copy to `.env`

## 💡 Tips & Best Practices

### Cost Optimization
- The agent only sends identified balance sheet pages to ADE (not entire documents)
- Use page detection to minimize ADE credit usage
- Check ADE credits before processing large batches

### Debugging
- Review annotated PNG images in `temp_ade_pages/` to see what ADE detected
- Inspect single-page PDFs to verify correct page identification
- Check console output for detailed processing logs

### Common Issues

**Issue**: No balance sheets detected
- **Solution**: Check if PDF contains text-based tables (not scanned images)
- Verify keywords like "Balance Sheet" or "Assets" appear in text

**Issue**: ADE credit exhaustion
- **Solution**: Agent checks credits automatically - add more credits before processing

**Issue**: Incorrect table structure in Excel
- **Solution**: Review annotated images to see if ADE detected correct boundaries
- May need to adjust ADE model or page preprocessing

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Support for Income Statements and Cash Flow Statements
- Multi-language support
- Additional PDF layout formats
- Enhanced validation rules
- Automated accuracy testing suite

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- **LangChain**: Agent orchestration framework
- **Anthropic Claude**: LLM for page identification and reasoning
- **Landing AI ADE**: High-accuracy document table extraction
- **PyMuPDF**: PDF processing and manipulation
- **Pandas**: Data structuring and Excel export

## 📞 Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Review [EVALUATION_FRAMEWORK.md](EVALUATION_FRAMEWORK.md) for testing guidance
- Check annotated images in `temp_ade_pages/` for debugging

---

**Status**: Active Development | **Version**: 1.0.0 | **Last Updated**: January 2026
