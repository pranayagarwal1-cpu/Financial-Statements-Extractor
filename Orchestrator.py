"""
Orchestrator Agent — Financial Statements Pipeline

An LLM-based agent that coordinates two sub-agents:
  - Extraction Agent  (AI Agent.py)        — extracts balance sheets from PDFs
  - Evaluation Agent  (Evaluation Agent.py) — evaluates extraction quality

Usage:
    python Orchestrator.py extract    # run extraction only
    python Orchestrator.py evaluate   # run evaluation only
    python Orchestrator.py full       # run both in sequence
"""

import os
import sys
import json
import importlib.util
from pathlib import Path
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

load_dotenv(override=True)

BASE_DIR = Path(__file__).parent

EXTRACTION_TASK = """
Process all PDF files in input_files/ and extract balance sheet data.

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

EVALUATION_TASK = """
Evaluate every Excel file produced by the Extraction Agent.

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


# ============================================================================
# MODULE LOADER
# ============================================================================

def _load_module(module_name: str, file_path: str):
    """Load a Python module from a file path that may contain spaces."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ============================================================================
# ORCHESTRATOR TOOLS  (sub-agents called as tools)
# ============================================================================

@tool
def run_extraction(task: str) -> str:
    """
    Invokes the Extraction Agent to extract balance sheet data from all PDFs
    in input_files/ and save Excel files to output_excel/.

    Args:
        task: Detailed instructions to pass to the Extraction Agent.

    Returns:
        JSON string with status and a summary of what the agent did.
    """
    print("\n" + "=" * 60)
    print("📥  EXTRACTION AGENT  starting…")
    print("=" * 60)
    try:
        agent = _load_module("ai_agent", str(BASE_DIR / "AI Agent.py"))
        result = agent.run_agent(task, max_iterations=25)
        output = result.get("output", "")
        print("\n✅  EXTRACTION AGENT  finished.")
        return json.dumps({"status": "success", "output": output})
    except Exception as e:
        import traceback
        return json.dumps({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        })


@tool
def run_evaluation(task: str) -> str:
    """
    Invokes the Evaluation Agent to assess the quality of extracted Excel files
    and save a scored report to output_excel/.

    Args:
        task: Detailed instructions to pass to the Evaluation Agent.

    Returns:
        JSON string with status and the agent's final verdict.
    """
    print("\n" + "=" * 60)
    print("🔍  EVALUATION AGENT  starting…")
    print("=" * 60)
    try:
        agent = _load_module("evaluation_agent", str(BASE_DIR / "Evaluation Agent.py"))
        result = agent.run_evaluation_agent(task, max_iterations=25)
        output = result.get("output", "")
        print("\n✅  EVALUATION AGENT  finished.")
        return json.dumps({"status": "success", "output": output})
    except Exception as e:
        import traceback
        return json.dumps({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        })


# ============================================================================
# ORCHESTRATOR AGENT
# ============================================================================

tools = [run_extraction, run_evaluation]

llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)
llm_with_tools = llm.bind_tools(tools)

SYSTEM_PROMPT = """You are the Orchestrator Agent for a financial statements extraction pipeline.

You coordinate two specialised sub-agents:
- run_extraction  — extracts balance sheet tables from PDFs and saves Excel files
- run_evaluation  — evaluates extraction quality and saves a scored report

Rules:
- When asked to EXTRACT: call run_extraction with the provided task.
- When asked to EVALUATE: call run_evaluation with the provided task.
- When asked to run the FULL pipeline: call run_extraction first, wait for it to
  succeed, then call run_evaluation.
- If a sub-agent returns an error, report it clearly and do not proceed further.
- After all tools have finished, provide a concise summary of what was done and
  the outcome."""


def run_orchestrator(task: str, max_iterations: int = 10) -> dict:
    """
    Runs the Orchestrator Agent.

    Args:
        task:           High-level instruction (extract / evaluate / full pipeline).
        max_iterations: Safety cap on LLM iterations.

    Returns:
        dict with key "output" containing the agent's final response.
    """
    print("=" * 70)
    print("🎯  ORCHESTRATOR AGENT")
    print("=" * 70)
    print(f"Task: {task.strip()}\n")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=task),
    ]

    for iteration in range(1, max_iterations + 1):
        print(f"\n--- Orchestrator iteration {iteration} ---")
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            print("\n✅  Orchestrator finished.")
            print(f"💬  {response.content}")
            return {"output": response.content}

        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            print(f"🎯  Dispatching → {tool_name}")

            tool_func = next((t for t in tools if t.name == tool_name), None)
            if tool_func:
                try:
                    observation = tool_func.invoke(tool_args)
                    messages.append(ToolMessage(content=observation, tool_call_id=tc["id"]))
                except Exception as e:
                    messages.append(ToolMessage(content=f"Error: {e}", tool_call_id=tc["id"]))
            else:
                messages.append(ToolMessage(content=f"Unknown tool: {tool_name}", tool_call_id=tc["id"]))

    print(f"\n⚠️  Max iterations ({max_iterations}) reached.")
    return {"output": "Orchestrator reached max iterations without completing."}


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"

    if mode == "extract":
        task = f"Extract balance sheet data from all PDFs.\n\n{EXTRACTION_TASK}"
    elif mode == "evaluate":
        task = f"Evaluate the extracted Excel files.\n\n{EVALUATION_TASK}"
    else:  # full
        task = (
            "Run the full pipeline: first extract balance sheet data from all PDFs, "
            "then evaluate the extraction quality.\n\n"
            f"Extraction instructions:\n{EXTRACTION_TASK}\n\n"
            f"Evaluation instructions:\n{EVALUATION_TASK}"
        )

    result = run_orchestrator(task)

    print("\n" + "=" * 70)
    print("🎉  PIPELINE COMPLETE")
    print("=" * 70)
    print(result.get("output", ""))
