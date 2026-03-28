"""
Sequential Pipeline: Extraction Agent → Evaluation Agent

Runs both agents in order:
  1. AI Agent.py     — extracts balance sheets from PDFs, writes extraction_manifest.json
  2. Evaluation Agent.py — reads the manifest, evaluates quality, writes evaluation report

Usage:
    python pipeline.py
"""

import sys
import os
import importlib.util


def load_module(module_name: str, file_path: str):
    """Load a Python module from a file path that may contain spaces."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 70)
    print("🚀 FINANCIAL STATEMENTS PIPELINE")
    print("   Step 1 of 2 — Extraction  |  Step 2 of 2 — Evaluation")
    print("=" * 70)

    # ── Step 1: Extraction Agent ──────────────────────────────────────────────
    print("\n📥 Loading Extraction Agent...")
    extraction_agent = load_module(
        "ai_agent",
        os.path.join(base_dir, "AI Agent.py"),
    )

    extraction_task = """
    Process all PDF files in the current folder and extract balance sheet data.

    For each PDF:
    1. Check ADE credits first before reading pdf content from input_files/.
    2. Identify which pages contain the balance sheet.
    3. Extract each balance sheet page separately and send ONE PAGE AT A TIME to ADE.
    4. Save temporary single-page PDFs to intermediate_files/ for inspection.
    5. Save annotated images showing chunk boundaries alongside each temp PDF.
    6. Save the extracted data to Excel in the output_excel/ folder.
    7. Ensure no data loss and maintain structural integrity.

    IMPORTANT: As your very last action, call write_extraction_manifest() to
    create the handoff file for the Evaluation Agent.

    Provide a brief summary when complete.
    """

    extraction_result = extraction_agent.run_agent(extraction_task, max_iterations=25)

    print("\n" + "=" * 70)
    print("✅ EXTRACTION COMPLETE")
    print("=" * 70)
    print(f"Summary: {extraction_result.get('output', 'No output')[:500]}")

    # ── Step 2: Evaluation Agent ──────────────────────────────────────────────
    print("\n\n📊 Loading Evaluation Agent...")
    evaluation_agent = load_module(
        "evaluation_agent",
        os.path.join(base_dir, "Evaluation Agent.py"),
    )

    evaluation_task = """
    The Extraction Agent has just finished running.

    Evaluate every Excel file it produced:
    1. Read the extraction manifest from intermediate_files/extraction_manifest.json
       to discover which files were created and which PDF pages they came from.
    2. For each Excel file:
       - Inspect its structure.
       - Validate the accounting equation (Assets = Liabilities + Equity).
       - Score completeness and data quality.
       - Cross-reference key totals against the source PDF pages.
    3. Build an overall_summary with aggregate metrics.
    4. Save the full evaluation report to output_excel/.
    5. Print the final verdict.
    """

    evaluation_result = evaluation_agent.run_evaluation_agent(
        evaluation_task, max_iterations=25
    )

    # ── Final combined summary ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("🎉 PIPELINE COMPLETE")
    print("=" * 70)
    print("\nExtraction summary:")
    print(extraction_result.get("output", "No output")[:400])
    print("\nEvaluation verdict:")
    print(evaluation_result.get("output", "No output")[:400])
    print("\nReports saved to: output_excel/")
    print("=" * 70)


if __name__ == "__main__":
    main()
