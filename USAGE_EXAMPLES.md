# Usage Examples

This guide provides step-by-step examples for using the Financial Statements Extractor.

## Table of Contents
- [Quick Start Example](#quick-start-example)
- [Understanding the Output](#understanding-the-output)
- [Advanced Usage Examples](#advanced-usage-examples)
- [Debugging and Troubleshooting](#debugging-and-troubleshooting)

---

## Quick Start Example

### Step 1: Prepare Your PDFs

Place your financial PDF documents in the project directory:

```
financial-statements-extractor/
├── AI Agent.py
├── Alliander-Half-Year-Report-2025.pdf  ← Your PDF here
└── AnnualReport2024.pdf                  ← Another PDF
```

### Step 2: Run the Agent

```bash
python "AI Agent.py"
```

### Step 3: Expected Console Output

```
======================================================================
🤖 BALANCE SHEET EXTRACTION AGENT
======================================================================
Task: Process all PDF files...

--- Iteration 1 ---
🔧 Tool: check_ade_credits
📥 Args: {}
📤 Output: {"status": "success", "message": "Landing AI ADE is accessible"}

--- Iteration 2 ---
🔧 Tool: list_pdf_files_in_folder
📥 Args: {"folder_path": "."}
📤 Output: {"status": "success", "count": 2, "files": ["Alliander-Half-Year-Report-2025.pdf", "AnnualReport2024.pdf"]}

--- Iteration 3 ---
🔧 Tool: extract_text_from_pdf_pages
📥 Args: {"pdf_filename": "Alliander-Half-Year-Report-2025.pdf", "max_pages": 50}
📤 Output: {"status": "success", "total_pages": 45, "pages": [...]}

--- Iteration 4 ---
🔧 Tool: identify_balance_sheet_pages
📥 Args: {"pdf_filename": "Alliander-Half-Year-Report-2025.pdf", "pages_text_data": "..."}
📤 Output: {"status": "success", "pages": [22, 23], "confidence": "high"}

--- Iteration 5 ---
🔧 Tool: extract_balance_sheet_with_ade
📥 Args: {"pdf_filename": "Alliander-Half-Year-Report-2025.pdf", "page_numbers": "[22, 23]"}
    📄 Extracting 2 page(s) from Alliander-Half-Year-Report-2025.pdf for ADE processing
      → Saved temp PDF for inspection: temp_ade_pages/Alliander-Half-Year-Report-2025_page22_for_ADE.pdf
      → Sending to ADE for processing...
      → Saved annotated image: temp_ade_pages/Alliander-Half-Year-Report-2025_page22_for_ADE_annotated.png
      📊 Found table chunk on page 22
      ✅ Confirmed as Balance Sheet table
      ✅ Extracted table with 45 rows on page 22
📤 Output: {"status": "success", "tables_found": 2, "tables": [...]}

--- Iteration 6 ---
🔧 Tool: parse_and_save_to_excel
📥 Args: {"pdf_filename": "Alliander-Half-Year-Report-2025.pdf", "extracted_data": "..."}
📤 Output: {"status": "success", "message": "Successfully saved 2 balance sheet table(s)", "output_file": "output_excel/Alliander-Half-Year-Report-2025_balance_sheet.xlsx"}

✅ Agent finished!
💬 Final response: Successfully processed all PDFs. Balance sheets extracted and saved.

======================================================================
🎉 PROCESSING COMPLETE
======================================================================
```

---

## Understanding the Output

### Generated Files Structure

After running, you'll see:

```
financial-statements-extractor/
├── output_excel/
│   └── Alliander-Half-Year-Report-2025_balance_sheet.xlsx  ← Final extracted data
│
└── temp_ade_pages/
    ├── Alliander-Half-Year-Report-2025_page22_for_ADE.pdf          ← Single-page PDF sent to ADE
    ├── Alliander-Half-Year-Report-2025_page22_for_ADE_annotated.png ← Visual debugging
    ├── Alliander-Half-Year-Report-2025_page23_for_ADE.pdf
    └── Alliander-Half-Year-Report-2025_page23_for_ADE_annotated.png
```

### Excel Output Format

The extracted Excel file contains:
- **Sheet name**: `Page22`, `Page23` (one sheet per balance sheet table)
- **Structure**: Headers in first row, data in subsequent rows
- **Formatting**: Clean columns with proper alignment

Example structure:
```
| Description              | 30 June 2025 | 31 December 2024 |
|--------------------------|--------------|------------------|
| Assets                   |              |                  |
| Non-current assets       |              |                  |
| Property, plant & equip  | 8,456        | 8,234           |
| Intangible assets        | 234          | 245             |
| ...                      | ...          | ...             |
```

### Annotated Images

The PNG files show:
- **Blue boxes**: Detected table chunks
- **Green boxes**: Text chunks
- **Purple boxes**: Marginalia
- **Labels**: Chunk type and ID for debugging

---

## Advanced Usage Examples

### Example 1: Process Single PDF with Specific Pages

Edit `AI Agent.py` at the bottom:

```python
if __name__ == "__main__":
    task = """
    Process only the file: Q4-2024-Report.pdf
    Extract balance sheet from pages 18-20 only.
    """

    result = run_agent(task, max_iterations=15)
```

### Example 2: Custom Output Folder

Modify configuration in `AI Agent.py`:

```python
# At top of file
INPUT_FOLDER = "./input_pdfs"        # Custom input folder
OUTPUT_FOLDER = "./extracted_data"   # Custom output folder
TEMP_ADE_FOLDER = "./debug_output"   # Custom temp folder
```

### Example 3: Using ADE.py Directly (No Agent)

If you know exactly which pages to extract:

1. Edit `ADE.py` to specify your PDF and page numbers
2. Run: `python ADE.py`
3. Faster but requires manual page identification

### Example 4: Batch Processing with Custom Logic

Create a custom script:

```python
from AI Agent import run_agent

pdf_files = [
    "Company_A_2024.pdf",
    "Company_B_2024.pdf",
    "Company_C_2024.pdf"
]

for pdf in pdf_files:
    task = f"Extract balance sheet from {pdf}"
    result = run_agent(task, max_iterations=15)
    print(f"Completed: {pdf}")
```

---

## Debugging and Troubleshooting

### Debug Strategy 1: Visual Inspection

When extraction doesn't look right:

1. Open the annotated PNG file in `temp_ade_pages/`
2. Check if blue boxes (tables) cover the correct areas
3. If boxes are wrong, it's an ADE detection issue
4. If boxes are correct but extraction is wrong, it's a parsing issue

**Example**: If balance sheet numbers are missing, check if ADE detected the table chunk.

### Debug Strategy 2: Console Output Analysis

Look for these key indicators:

```
✅ Confirmed as Balance Sheet table    ← Good: Table validated
⏭️  Table doesn't match criteria       ← Issue: Wrong table detected
❌ Failed to parse table data          ← Issue: Parsing problem
```

### Debug Strategy 3: Inspect Temp PDFs

Open the single-page PDFs in `temp_ade_pages/`:
- Verify the correct page was extracted
- Check if text is selectable (not scanned image)
- Confirm table is clearly visible

### Common Issues and Solutions

#### Issue 1: "No balance sheets detected"

**Symptoms**:
```
📤 Output: {"status": "no_balance_sheet", "pages": []}
```

**Causes**:
- PDF contains scanned images, not text
- Balance sheet uses non-standard terminology
- Pages don't contain keywords like "Assets" or "Liabilities"

**Solutions**:
1. Check if PDF is searchable (Ctrl+F for "Assets")
2. If scanned, use OCR first
3. Manually specify pages: modify task to include page numbers

#### Issue 2: "ADE credits exhausted"

**Symptoms**:
```
📤 Output: {"status": "insufficient_credits", "message": "Landing AI ADE credits exhausted"}
```

**Solutions**:
1. Visit Landing AI dashboard
2. Add more credits
3. Re-run the agent (it will resume from where it stopped)

#### Issue 3: Excel structure is incorrect

**Symptoms**:
- Headers misaligned with data
- Numbers in wrong columns
- Missing rows

**Solutions**:
1. Check annotated PNG - did ADE detect the correct table boundaries?
2. Review console output for parsing warnings
3. Open temp PDF - is the table complex (merged cells, nested headers)?
4. For complex tables, may need manual post-processing

#### Issue 4: Processing takes too long

**Symptoms**:
- Agent iterates many times
- No progress for several minutes

**Solutions**:
1. Check max_iterations parameter (default 20)
2. Reduce max_pages in extract_text_from_pdf_pages (default 50)
3. Specify exact page numbers if known
4. Check network connectivity to API services

---

## Performance Tips

### Tip 1: Pre-identify Pages
If you know page numbers, modify the task:
```python
task = "Extract balance sheet from pages 22-23 of Report.pdf"
```
This skips the LLM page identification step.

### Tip 2: Process in Batches
For many PDFs, process 10 at a time to monitor quality before bulk processing.

### Tip 3: Keep Temp Files
The temp files in `temp_ade_pages/` are invaluable for debugging. Don't delete them until you've verified the extraction quality.

### Tip 4: Test on Simple Documents First
Start with well-formatted, single-page balance sheets before attempting complex multi-page consolidated statements.

---

## Example Workflow

Here's a complete workflow from start to finish:

```bash
# 1. Setup
cd financial-statements-extractor
source venv/bin/activate

# 2. Add your PDFs
cp ~/Downloads/FinancialReport.pdf .

# 3. Run extraction
python "AI Agent.py"

# 4. Review output
open output_excel/FinancialReport_balance_sheet.xlsx

# 5. Debug if needed
open temp_ade_pages/FinancialReport_page22_for_ADE_annotated.png

# 6. Validate data
# Check if Assets = Liabilities + Equity in Excel

# 7. Clean up (optional)
# rm temp_ade_pages/*.pdf temp_ade_pages/*.png
```

---

## Next Steps

- Review [EVALUATION_FRAMEWORK.md](EVALUATION_FRAMEWORK.md) to measure accuracy
- Experiment with different PDF formats
- Build your own evaluation dataset
- Customize parsing logic for your specific needs

---

**Need help?** Open an issue on GitHub with:
1. Console output
2. Sample PDF (if not confidential)
3. Annotated PNG showing detection
4. Description of expected vs actual behavior
