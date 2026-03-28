"""
LangChain Evaluation Agent for Balance Sheet Extraction Quality Assessment

Collaborates with AI Agent.py (the Extraction Agent):
  - Reads the extraction_manifest.json written by the Extraction Agent
  - Evaluates every extracted Excel file for accuracy, completeness, and integrity
  - Cross-references key totals against the original PDF using Claude
  - Produces a scored evaluation report (JSON + Markdown)

Run standalone:
    python "Evaluation Agent.py"

Or let pipeline.py orchestrate both agents sequentially.
"""

import os
import re
import glob
import json
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

import pandas as pd
import pymupdf

load_dotenv(override=True)

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

# ============================================================================
# CONFIGURATION  (must match AI Agent.py)
# ============================================================================

INPUT_FOLDER = "input_files"
OUTPUT_FOLDER = "output_excel"
INTERMEDIATE_FILES = "intermediate_files"
EVALUATION_FOLDER = "intermediate_files"
MANIFEST_PATH = os.path.join(INTERMEDIATE_FILES, "extraction_manifest.json")

# ============================================================================
# EVALUATION TOOLS
# ============================================================================

@tool
def read_extraction_manifest(manifest_path: str = MANIFEST_PATH) -> str:
    """
    Reads the extraction manifest written by the Extraction Agent.
    The manifest lists which PDFs were processed, which pages were extracted,
    and which Excel files were created.

    If no manifest exists, falls back to discovering Excel files directly.

    Args:
        manifest_path: Path to extraction_manifest.json (default: intermediate_files/extraction_manifest.json)

    Returns:
        JSON string with manifest data, including excel_outputs and pages_extracted.
    """
    try:
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            return json.dumps({"status": "success", "manifest": manifest})

        # Fallback: scan folders directly
        excel_files = glob.glob(os.path.join(OUTPUT_FOLDER, "*.xlsx"))
        source_pdfs = glob.glob(os.path.join(INPUT_FOLDER, "*.pdf"))
        temp_pdfs = glob.glob(os.path.join(INTERMEDIATE_FILES, "*.pdf"))

        pages_by_source: dict = {}
        for temp_pdf in temp_pdfs:
            name = os.path.basename(temp_pdf)
            match = re.search(r"_page(\d+)_for_ADE", name)
            if match:
                page_num = int(match.group(1))
                base = name[: name.rfind("_page")]
                pages_by_source.setdefault(base, [])
                if page_num not in pages_by_source[base]:
                    pages_by_source[base].append(page_num)

        manifest = {
            "timestamp": None,
            "input_folder": INPUT_FOLDER,
            "output_folder": OUTPUT_FOLDER,
            "temp_folder": INTERMEDIATE_FILES,
            "source_pdfs": [os.path.basename(p) for p in source_pdfs],
            "excel_outputs": [os.path.basename(e) for e in excel_files],
            "pages_extracted": pages_by_source,
        }
        return json.dumps({
            "status": "no_manifest_fallback",
            "message": "No manifest found — discovered files directly",
            "manifest": manifest,
        })

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def load_and_inspect_excel(excel_filename: str) -> str:
    """
    Loads an extracted Excel file and returns structural information:
    sheet names, dimensions, column names, and sample rows.

    Args:
        excel_filename: Filename (e.g. 'report_balance_sheet.xlsx') or full path.

    Returns:
        JSON string with per-sheet structure details.
    """
    try:
        excel_path = (
            excel_filename
            if os.path.isabs(excel_filename)
            else os.path.join(OUTPUT_FOLDER, excel_filename)
        )
        if not os.path.exists(excel_path):
            return json.dumps({"status": "error", "message": f"File not found: {excel_path}"})

        xl = pd.ExcelFile(excel_path)
        sheets_info = []

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)
            sheets_info.append({
                "sheet_name": sheet_name,
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": list(df.columns),
                "sample_head": df.head(5).fillna("").astype(str).values.tolist(),
                "sample_tail": df.tail(3).fillna("").astype(str).values.tolist(),
                "non_empty_cells": int(df.notna().sum().sum()),
                "total_cells": int(df.size),
            })

        return json.dumps({"status": "success", "filename": excel_filename, "sheets": sheets_info})

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def validate_accounting_equation(excel_filename: str) -> str:
    """
    Validates the fundamental accounting equation:
        Total Assets = Total Liabilities + Total Equity

    Uses Claude as judge to identify the correct totals from the balance sheet,
    avoiding brittle keyword matching that confuses subtotals with grand totals.

    Args:
        excel_filename: Filename (or full path) of the Excel file.

    Returns:
        JSON string with per-sheet validation results.
    """
    try:
        excel_path = (
            excel_filename
            if os.path.isabs(excel_filename)
            else os.path.join(OUTPUT_FOLDER, excel_filename)
        )
        if not os.path.exists(excel_path):
            return json.dumps({"status": "error", "message": f"File not found: {excel_path}"})

        xl = pd.ExcelFile(excel_path)
        results = []
        llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)
            if df.empty or len(df.columns) < 2:
                results.append({"sheet": sheet_name, "status": "skipped", "reason": "too small"})
                continue

            sheet_text = df.fillna("").astype(str).to_string(max_rows=100, max_cols=8)

            prompt = f"""You are an accounting expert. Examine this balance sheet data and validate the accounting equation.

BALANCE SHEET DATA (sheet: {sheet_name}):
{sheet_text}

Find the GRAND TOTAL rows only (not subtotals like "Total Current Assets" or "Total Current Liabilities"):
- Total Assets (the final sum of all assets)
- Total Liabilities and Equity (or equivalent: the final balancing figure)

For each reporting period/column found, check if Total Assets = Total Liabilities + Equity.

Respond with ONLY a JSON object — no markdown, no commentary:
{{
    "periods_found": ["list of period labels, e.g. 2024, 2023"],
    "total_assets": {{"label": "exact row label", "values": {{"2024": 99467, "2023": 100495}}}},
    "total_liabilities_equity": {{"label": "exact row label", "values": {{"2024": 99467, "2023": 100495}}}},
    "equation_holds": true,
    "differences": {{"2024": 0, "2023": 0}},
    "verdict": "pass" | "fail" | "cannot_determine",
    "notes": "brief explanation if equation does not hold or data is ambiguous"
}}"""

            response = llm.invoke(prompt)
            response_text = response.content.strip()

            for fence in ("```json", "```"):
                if fence in response_text:
                    start = response_text.find(fence) + len(fence)
                    end = response_text.find("```", start)
                    response_text = response_text[start:end].strip()
                    break

            try:
                verdict = json.loads(response_text)
                results.append({
                    "sheet": sheet_name,
                    "status": "validated",
                    **verdict,
                })
            except json.JSONDecodeError:
                results.append({
                    "sheet": sheet_name,
                    "status": "parse_error",
                    "raw_response": response_text,
                })

        return json.dumps({"status": "success", "filename": excel_filename, "validation_results": results})

    except Exception as e:
        import traceback
        return json.dumps({"status": "error", "message": str(e), "traceback": traceback.format_exc()})


@tool
def check_completeness_and_quality(excel_filename: str) -> str:
    """
    Scores each sheet in the Excel file on two dimensions:

    Completeness (0–100 %):
      - Are all three balance-sheet sections present (Assets, Liabilities, Equity)?

    Data Quality:
      - Cell fill rate (% non-null)
      - Numeric parseability of data columns (% values that are valid numbers)
      - Row and column count sanity

    Args:
        excel_filename: Filename (or full path) of the Excel file.

    Returns:
        JSON string with per-sheet scores and a list of issues found.
    """
    SECTION_KWS = {
        "assets": ["asset", "current asset", "non-current asset", "fixed asset", "property"],
        "liabilities": ["liab", "payable", "debt", "borrow", "provision"],
        "equity": ["equity", "capital", "reserve", "retained", "shareholders", "stockholders"],
    }

    try:
        excel_path = (
            excel_filename
            if os.path.isabs(excel_filename)
            else os.path.join(OUTPUT_FOLDER, excel_filename)
        )
        if not os.path.exists(excel_path):
            return json.dumps({"status": "error", "message": f"File not found: {excel_path}"})

        xl = pd.ExcelFile(excel_path)
        sheet_results = []

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)
            if df.empty:
                sheet_results.append({"sheet": sheet_name, "status": "empty"})
                continue

            # --- Section completeness ---
            text = " ".join(df.iloc[:, 0].astype(str).str.lower().tolist())
            sections_found = {
                s: any(kw in text for kw in kws)
                for s, kws in SECTION_KWS.items()
            }
            completeness_score = round(sum(sections_found.values()) / 3 * 100, 1)

            # --- Fill rate ---
            fill_rate = round(df.notna().sum().sum() / max(df.size, 1) * 100, 1)

            # --- Numeric parseability of data columns ---
            numeric_score = None
            if len(df.columns) > 1:
                parseable = total_non_empty = 0
                for col in df.columns[1:]:
                    for val in df[col]:
                        if pd.notna(val) and str(val).strip():
                            total_non_empty += 1
                            s = re.sub(r"[€$£¥,\s()\-]", "", str(val))
                            try:
                                float(s)
                                parseable += 1
                            except ValueError:
                                pass
                if total_non_empty > 0:
                    numeric_score = round(parseable / total_non_empty * 100, 1)

            issues = []
            if len(df) < 10:
                issues.append(f"Only {len(df)} rows — may be incomplete")
            if not (2 <= len(df.columns) <= 8):
                issues.append(f"Unusual column count: {len(df.columns)}")
            missing = [s for s, found in sections_found.items() if not found]
            if missing:
                issues.append(f"Missing sections: {missing}")

            sheet_results.append({
                "sheet": sheet_name,
                "row_count": len(df),
                "column_count": len(df.columns),
                "sections_found": sections_found,
                "completeness_score_pct": completeness_score,
                "fill_rate_pct": fill_rate,
                "numeric_parseability_pct": numeric_score,
                "issues": issues,
            })

        return json.dumps({"status": "success", "filename": excel_filename, "sheet_results": sheet_results})

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def cross_reference_with_source_pdf(
    excel_filename: str,
    pdf_filename: str,
    page_numbers: str,
) -> str:
    """
    Spot-checks the extracted Excel against the original PDF using Claude.

    Reads the raw text from the specified source PDF pages and asks the LLM
    to verify whether:
      - Key totals (Total Assets, Total Equity) match
      - Column headers / period dates are correct
      - Any values look garbled or missing

    Args:
        excel_filename: Filename of the extracted Excel file.
        pdf_filename:   Filename of the source PDF (in INPUT_FOLDER).
        page_numbers:   JSON list of page numbers that were extracted, e.g. "[22]".

    Returns:
        JSON string with the LLM's structured cross-reference verdict.
    """
    try:
        excel_path = (
            excel_filename
            if os.path.isabs(excel_filename)
            else os.path.join(OUTPUT_FOLDER, excel_filename)
        )
        pdf_path = (
            pdf_filename
            if os.path.isabs(pdf_filename)
            else os.path.join(INPUT_FOLDER, pdf_filename)
        )
        pages = json.loads(page_numbers) if isinstance(page_numbers, str) else page_numbers

        if not os.path.exists(excel_path):
            return json.dumps({"status": "error", "message": f"Excel not found: {excel_path}"})
        if not os.path.exists(pdf_path):
            return json.dumps({"status": "error", "message": f"PDF not found: {pdf_path}"})

        # Extract text from relevant PDF pages
        doc = pymupdf.open(pdf_path)
        pdf_sections = []
        for pn in pages:
            if 0 < pn <= len(doc):
                text = doc[pn - 1].get_text("text")
                pdf_sections.append(f"--- Page {pn} ---\n{text[:3000]}")
        doc.close()

        if not pdf_sections:
            return json.dumps({"status": "error", "message": "Could not extract PDF text for given pages"})

        pdf_text = "\n\n".join(pdf_sections)

        # Build a compact text representation of the Excel
        xl = pd.ExcelFile(excel_path)
        excel_summaries = []
        for sn in xl.sheet_names:
            df = xl.parse(sn)
            excel_summaries.append(f"Sheet '{sn}':\n{df.to_string(max_rows=60, max_cols=6)}")
        excel_text = "\n\n".join(excel_summaries)

        llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

        prompt = f"""You are an auditor evaluating the quality of an automated balance sheet extraction.

PDF TEXT (source of truth — first {len(pdf_text)} chars):
{pdf_text[:4000]}

EXTRACTED EXCEL DATA:
{excel_text[:3000]}

Compare the two and answer:
1. Do the key totals (Total Assets, Total Equity / Total Equity & Liabilities) match?
2. Are column headers (e.g. reporting dates) correctly captured?
3. Are there any obviously missing rows, garbled numbers, or structural problems?

Respond with ONLY a JSON object — no markdown, no commentary:
{{
    "verdict": "pass" | "partial" | "fail",
    "confidence": "high" | "medium" | "low",
    "total_assets_match": true | false | null,
    "total_equity_match": true | false | null,
    "headers_correct": true | false | null,
    "issues_found": ["list specific issues, or empty list if none"],
    "summary": "one concise sentence describing extraction quality"
}}"""

        response = llm.invoke(prompt)
        response_text = response.content.strip()

        # Strip markdown code fences if present
        for fence in ("```json", "```"):
            if fence in response_text:
                start = response_text.find(fence) + len(fence)
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
                break

        verdict = json.loads(response_text)

        return json.dumps({
            "status": "success",
            "excel_file": excel_filename,
            "pdf_file": pdf_filename,
            "pages_checked": pages,
            "cross_reference": verdict,
        })

    except Exception as e:
        import traceback
        return json.dumps({"status": "error", "message": str(e), "traceback": traceback.format_exc()})


@tool
def save_evaluation_report(evaluation_json: str) -> str:
    """
    Saves the complete evaluation results as:
      - intermediate_files/evaluation_report_<timestamp>.json
      - intermediate_files/evaluation_report_<timestamp>.md
      - intermediate_files/evaluation_report_latest.json  (overwritten each run)
      - intermediate_files/evaluation_report_latest.md

    Args:
        evaluation_json: JSON string with the full evaluation results dict.

    Returns:
        JSON string with paths to the saved files.
    """
    try:
        results = json.loads(evaluation_json)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        json_path = os.path.join(EVALUATION_FOLDER, f"evaluation_report_{ts}.json")
        md_path = os.path.join(EVALUATION_FOLDER, f"evaluation_report_{ts}.md")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # ── Build Markdown ──────────────────────────────────────────────────
        lines = [
            "# Balance Sheet Extraction — Evaluation Report",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
            "---",
            "",
            "## Overall Summary",
            "",
        ]

        overall = results.get("overall_summary", {})
        lines += [
            "| Metric | Value |",
            "|--------|-------|",
            f"| Files evaluated | {overall.get('files_evaluated', 'N/A')} |",
            f"| Accounting equation pass rate | {overall.get('accounting_pass_rate', 'N/A')} |",
            f"| Average completeness | {overall.get('avg_completeness_pct', 'N/A')} % |",
            f"| Average numeric quality | {overall.get('avg_numeric_quality_pct', 'N/A')} % |",
            f"| LLM cross-reference verdict | {overall.get('cross_reference_verdict', 'N/A')} |",
            "",
        ]

        for fr in results.get("file_results", []):
            fname = fr.get("filename", "Unknown")
            lines += [f"## {fname}", ""]

            # Accounting validation
            acct = fr.get("accounting_validation", {})
            for sr in acct.get("validation_results", []):
                holds = sr.get("equation_holds")
                icon = "✅" if holds is True else ("❌" if holds is False else "⚠️")
                lines.append(f"**Accounting Equation ({sr.get('sheet')}):** {icon}")
                ta = sr.get("total_assets")
                tle = sr.get("total_liabilities_equity")
                if ta:
                    vals = ta.get("values") or {}
                    val_str = ", ".join(f"{k}: {v}" for k, v in vals.items()) if vals else ta.get("value", "N/A")
                    lines.append(f"- Total Assets: `{val_str}` ({ta.get('label', '')})")
                if tle:
                    vals = tle.get("values") or {}
                    val_str = ", ".join(f"{k}: {v}" for k, v in vals.items()) if vals else tle.get("value", "N/A")
                    lines.append(f"- Total Liabilities+Equity: `{val_str}` ({tle.get('label', '')})")
                diffs = sr.get("differences")
                if diffs:
                    diff_str = ", ".join(f"{k}: {v}" for k, v in diffs.items())
                    lines.append(f"- Differences: `{diff_str}`")
                if sr.get("notes"):
                    lines.append(f"- Note: {sr.get('notes')}")
                lines.append("")

            # Completeness & quality
            comp = fr.get("completeness_quality", {})
            for sr in comp.get("sheet_results", []):
                lines += [
                    f"**Data Quality ({sr.get('sheet')}):**",
                    f"- Completeness: `{sr.get('completeness_score_pct')} %`",
                    f"- Fill rate: `{sr.get('fill_rate_pct')} %`",
                    f"- Numeric parseability: `{sr.get('numeric_parseability_pct')} %`",
                    f"- Rows extracted: `{sr.get('row_count')}`",
                ]
                for issue in sr.get("issues", []):
                    lines.append(f"- ⚠️ {issue}")
                lines.append("")

            # Cross-reference
            xref_block = fr.get("cross_reference", {})
            xref = xref_block.get("cross_reference", {})
            if xref:
                icon = "✅" if xref.get("verdict") == "pass" else (
                    "⚠️" if xref.get("verdict") == "partial" else "❌"
                )
                lines += [
                    f"**LLM Cross-Reference:** {icon} {str(xref.get('verdict', '')).upper()}",
                    f"- Confidence: {xref.get('confidence', 'N/A')}",
                    f"- {xref.get('summary', '')}",
                ]
                for issue in xref.get("issues_found", []):
                    lines.append(f"  - {issue}")
                lines.append("")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # Copy to "latest" files
        latest_json = os.path.join(EVALUATION_FOLDER, "evaluation_report_latest.json")
        latest_md = os.path.join(EVALUATION_FOLDER, "evaluation_report_latest.md")
        shutil.copy2(json_path, latest_json)
        shutil.copy2(md_path, latest_md)

        return json.dumps({
            "status": "success",
            "json_report": json_path,
            "markdown_report": md_path,
            "latest_json": latest_json,
            "latest_md": latest_md,
        })

    except Exception as e:
        import traceback
        return json.dumps({"status": "error", "message": str(e), "traceback": traceback.format_exc()})


# ============================================================================
# AGENT SETUP
# ============================================================================

tools = [
    read_extraction_manifest,
    load_and_inspect_excel,
    validate_accounting_equation,
    check_completeness_and_quality,
    cross_reference_with_source_pdf,
    save_evaluation_report,
]

llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)
llm_with_tools = llm.bind_tools(tools)


def run_evaluation_agent(task: str, max_iterations: int = 25) -> dict:
    """
    Runs the evaluation agent to assess the outputs of the Extraction Agent.

    Args:
        task:           The task prompt handed to the agent.
        max_iterations: Safety limit on LLM iterations.

    Returns:
        dict with key "output" containing the agent's final text response.
    """
    print("=" * 70)
    print("🔍 BALANCE SHEET EVALUATION AGENT")
    print("=" * 70)
    print(f"Task: {task}\n")

    system_prompt = """You are a specialist AI agent that evaluates the quality of automated
balance sheet extractions produced by another AI agent.

Your job is to:
1. Read the extraction manifest to discover which Excel files were produced and
   which source PDF pages they came from.
2. For each Excel file:
   a. Inspect its structure with load_and_inspect_excel.
   b. Validate the accounting equation (Assets = Liabilities + Equity) with
      validate_accounting_equation.
   c. Score completeness and data quality with check_completeness_and_quality.
   d. Cross-reference key values against the source PDF with
      cross_reference_with_source_pdf — use the page numbers from the manifest.
3. Compile all results into an overall_summary dict that includes:
   - files_evaluated (int)
   - accounting_pass_rate (e.g. "1/1" or "100 %")
   - avg_completeness_pct (float)
   - avg_numeric_quality_pct (float)
   - cross_reference_verdict (e.g. "pass", "partial", "fail", "unable_to_verify")
   - final_verdict (MUST be exactly "pass" or "fail") — your overall judgement
     weighing all checks. Use "pass" if accounting equation holds and data is
     substantially complete, even if cross-reference could not run.
4. Call save_evaluation_report with a JSON string containing:
   {
     "overall_summary": { ... },
     "file_results": [
       {
         "filename": "...",
         "accounting_validation": <output of validate_accounting_equation>,
         "completeness_quality": <output of check_completeness_and_quality>,
         "cross_reference": <output of cross_reference_with_source_pdf>
       },
       ...
     ]
   }
5. Report the final evaluation verdict clearly.

Available tools:
- read_extraction_manifest:    Find out what was extracted (start here).
- load_and_inspect_excel:      Inspect structure of each Excel file.
- validate_accounting_equation: Check Assets = Liabilities + Equity.
- check_completeness_and_quality: Score sections, fill rate, numeric quality.
- cross_reference_with_source_pdf: LLM spot-check Excel vs PDF text.
- save_evaluation_report:      Save the final scored report (call this last).

Be thorough. Evaluate every Excel file listed in the manifest."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=task),
    ]

    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        print(f"\n--- Evaluation Iteration {iterations} ---")

        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                print(f"🔧 Tool: {tool_name}")
                print(f"📥 Args: {json.dumps(tool_args, indent=2)}")

                tool_func = next((t for t in tools if t.name == tool_name), None)
                if tool_func:
                    try:
                        observation = tool_func.invoke(tool_args)
                        preview = str(observation)
                        print(
                            f"📤 Output: {preview[:500]}..."
                            if len(preview) > 500
                            else f"📤 Output: {preview}"
                        )
                        messages.append(
                            ToolMessage(content=observation, tool_call_id=tool_call["id"])
                        )
                    except Exception as e:
                        err = f"Error executing tool: {e}"
                        print(f"❌ {err}")
                        messages.append(
                            ToolMessage(content=err, tool_call_id=tool_call["id"])
                        )
                else:
                    messages.append(
                        ToolMessage(
                            content=f"Error: Tool {tool_name} not found",
                            tool_call_id=tool_call["id"],
                        )
                    )
        else:
            print("\n✅ Evaluation Agent finished!")
            print(f"💬 Final response:\n{response.content}")
            return {"output": response.content}

    print(f"\n⚠️ Max iterations ({max_iterations}) reached")
    return {"output": "Max iterations reached without completion"}


# ============================================================================
# MAIN (standalone)
# ============================================================================

if __name__ == "__main__":
    task = """
    Evaluate the outputs produced by the Balance Sheet Extraction Agent.

    Steps:
    1. Read the extraction manifest from intermediate_files/extraction_manifest.json.
    2. For each Excel file listed in the manifest, run all evaluation checks.
    3. Cross-reference each Excel against its source PDF pages.
    4. Save a complete evaluation report to the intermediate_files/ folder.
    5. Print an overall verdict.
    """

    result = run_evaluation_agent(task)

    print("\n" + "=" * 70)
    print("📊 EVALUATION COMPLETE")
    print("=" * 70)
