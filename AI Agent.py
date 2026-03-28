"""
LangChain Orchestrated AI Agent for Balance Sheet Extraction

Architecture:
- Agent reads PDFs from input folder
- Identifies pages containing balance sheets using LLM
- Extracts balance sheets using Landing AI's ADE
- Parses and saves to Excel with structural integrity
"""

import os
import glob
import json
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import pymupdf
from typing import List, Dict, Any, Optional
from PIL import Image as PILImage, ImageDraw
from io import StringIO
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv(override=True)

# LangChain imports
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Landing AI ADE imports
from landingai_ade import LandingAIADE
from landingai_ade.types import ParseResponse

# ============================================================================
# CONFIGURATION
# ============================================================================

INPUT_FOLDER = "input_files"  # Folder containing PDFs
OUTPUT_FOLDER = "output_excel"  # Folder to save Excel files
INTERMEDIATE_FILES = "intermediate_files"  # Folder to save temp PDFs for inspection
ADE_MODEL = "dpt-2-latest"  # Landing AI ADE model

# Ensure folders exist
os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(INTERMEDIATE_FILES, exist_ok=True)

# Define colors for chunk types (same as helper.py)
CHUNK_TYPE_COLORS = {
    "chunkText": (40, 167, 69),        # Green
    "chunkTable": (0, 123, 255),       # Blue
    "chunkMarginalia": (111, 66, 193), # Purple
    "chunkFigure": (255, 0, 255),      # Magenta
    "chunkLogo": (144, 238, 144),      # Light green
    "chunkCard": (255, 165, 0),        # Orange
    "chunkAttestation": (0, 255, 255), # Cyan
    "chunkScanCode": (255, 193, 7),    # Yellow
    "chunkForm": (220, 20, 60),        # Red
    "tableCell": (173, 216, 230),      # Light blue
    "table": (70, 130, 180),           # Steel blue
}

def convert_html_table_to_markdown(html_content: str) -> str:
    """
    Converts ADE's HTML table output to clean markdown format.
    Handles colspan/rowspan attributes and intelligently processes headers.

    Args:
        html_content: HTML table string from ADE

    Returns:
        Clean markdown formatted table string (pipe-separated)
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        table = soup.find('table')

        if not table:
            return html_content

        # Extract all rows with cell metadata
        all_rows = []
        for tr in table.find_all('tr'):
            row_data = []
            for cell in tr.find_all(['td', 'th']):
                text = cell.get_text(strip=True)
                colspan = int(cell.get('colspan', 1))
                is_header = cell.name == 'th'
                row_data.append({
                    'text': text,
                    'colspan': colspan,
                    'is_header': is_header
                })
            if row_data:
                all_rows.append(row_data)

        if not all_rows:
            return html_content

        # Process rows into final structure
        rows = []

        for row_idx, row_data in enumerate(all_rows):
            cells = []

            # Check if this is a header row
            is_header_row = any(cell['is_header'] for cell in row_data)

            for cell_idx, cell in enumerate(row_data):
                text = cell['text']
                colspan = cell['colspan']

                if is_header_row and colspan > 1:
                    # For header rows with colspan:
                    # - If text is generic (like "€ million"), only add once and pad with empty
                    # - If text is specific (like a date), repeat it
                    is_generic = text.lower() in ['€ million', '€', 'million', '', 'eur', 'usd', '$']

                    if is_generic or not text:
                        # Add the text once, then empty cells
                        cells.append(text)
                        for _ in range(colspan - 1):
                            cells.append('')
                    else:
                        # Specific header (like date) - repeat it
                        for _ in range(colspan):
                            cells.append(text)
                else:
                    # Regular cells or no colspan - repeat as needed
                    for _ in range(colspan):
                        cells.append(text)

            if cells:
                rows.append(cells)

        # Find max columns and pad
        max_cols = max(len(row) for row in rows) if rows else 0

        for row in rows:
            while len(row) < max_cols:
                row.append('')

        # Convert to markdown format (pipe-separated)
        markdown_lines = []
        for i, row in enumerate(rows):
            # Create pipe-separated row
            markdown_lines.append('| ' + ' | '.join(row) + ' |')

            # Add separator after first row (header)
            if i == 0:
                markdown_lines.append('| ' + ' | '.join(['---'] * len(row)) + ' |')

        return '\n'.join(markdown_lines)

    except Exception as e:
        print(f"      ⚠️  HTML to markdown conversion failed: {str(e)}")
        # Fallback to original content
        return html_content


def save_annotated_image(parse_result: ParseResponse, document_path: str, output_path: str) -> None:
    """
    Creates and saves an annotated image with bounding boxes showing detected chunks.
    Based on draw_bounding_boxes from helper.py.

    Args:
        parse_result: ADE ParseResponse containing grounding info
        document_path: Path to the PDF file
        output_path: Path where to save the annotated PNG image
    """
    try:
        doc_path = Path(document_path)

        if doc_path.suffix.lower() == '.pdf':
            pdf = pymupdf.open(doc_path)

            # Process first page (since we're sending single-page PDFs)
            page = pdf[0]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))  # 2x scaling for better quality
            img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Create annotated image
            annotated_img = img.copy()
            draw = ImageDraw.Draw(annotated_img)

            img_width, img_height = img.size

            # Draw bounding boxes for all groundings
            for gid, grounding in (parse_result.grounding or {}).items():
                # Check if grounding belongs to page 0 (first page)
                if grounding.page != 0:
                    continue

                box = grounding.box

                # Extract normalized coordinates
                left, top, right, bottom = box.left, box.top, box.right, box.bottom

                # Convert to pixel coordinates
                x1 = int(left * img_width)
                y1 = int(top * img_height)
                x2 = int(right * img_width)
                y2 = int(bottom * img_height)

                # Draw bounding box with color based on chunk type
                color = CHUNK_TYPE_COLORS.get(grounding.type, (128, 128, 128))
                draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

                # Draw label background and text
                label = f"{grounding.type}:{gid}"
                label_y = max(0, y1 - 20)
                draw.rectangle([x1, label_y, x1 + len(label) * 8, y1], fill=color)
                draw.text((x1 + 2, label_y + 2), label, fill=(255, 255, 255))

            # Save annotated image
            annotated_img.save(output_path)
            pdf.close()

            return True
        else:
            print(f"      ⚠️  Unsupported file type for annotation: {doc_path.suffix}")
            return False

    except Exception as e:
        print(f"      ⚠️  Could not create annotated image: {str(e)}")
        return False

# ============================================================================
# AGENT TOOLS
# ============================================================================

@tool
def list_pdf_files_in_folder(folder_path: str = INPUT_FOLDER) -> str:
    """
    Lists all PDF files in the specified folder.

    Args:
        folder_path: Path to folder containing PDFs (default: current directory)

    Returns:
        JSON string with list of PDF filenames
    """
    try:
        pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
        if not pdf_files:
            return json.dumps({"status": "no_files", "message": f"No PDF files found in {folder_path}", "files": []})

        filenames = [os.path.basename(f) for f in pdf_files]
        return json.dumps({
            "status": "success",
            "count": len(filenames),
            "files": filenames
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e), "files": []})


@tool
def extract_text_from_pdf_pages(pdf_filename: str, max_pages: int = 50) -> str:
    """
    Extracts text from PDF pages to help identify which pages contain balance sheets.
    Returns text snippets from each page.

    Args:
        pdf_filename: Name of the PDF file in the input folder
        max_pages: Maximum number of pages to extract (default: 50)

    Returns:
        JSON string with page numbers and text snippets
    """
    try:
        pdf_path = os.path.join(INPUT_FOLDER, pdf_filename)
        if not os.path.exists(pdf_path):
            return json.dumps({"status": "error", "message": f"File not found: {pdf_filename}"})

        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        pages_data = []

        for page_num in range(min(total_pages, max_pages)):
            page = doc[page_num]
            text = page.get_text("text")

            # Get first 500 characters as snippet
            snippet = text[:500] if text else ""

            pages_data.append({
                "page_number": page_num + 1,
                "text_snippet": snippet,
                "has_keywords": any(keyword in text.lower() for keyword in [
                    'balance sheet', 'statement of financial position',
                    'assets', 'liabilities', 'equity'
                ])
            })

        doc.close()

        return json.dumps({
            "status": "success",
            "filename": pdf_filename,
            "total_pages": total_pages,
            "pages": pages_data
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def identify_balance_sheet_pages(pdf_filename: str, pages_text_data: str) -> str:
    """
    Uses LLM to analyze page text and identify which specific pages contain balance sheet tables.

    Args:
        pdf_filename: Name of the PDF file
        pages_text_data: JSON string from extract_text_from_pdf_pages

    Returns:
        JSON string with identified page numbers that contain balance sheets
    """
    try:
        data = json.loads(pages_text_data)
        if data.get("status") != "success":
            return pages_text_data  # Return error as is

        # Use LLM to identify balance sheet pages
        llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

        pages_info = []
        for page_data in data.get("pages", []):
            if page_data.get("has_keywords"):
                pages_info.append(f"Page {page_data['page_number']}: {page_data['text_snippet'][:300]}")

        if not pages_info:
            return json.dumps({
                "status": "no_balance_sheet",
                "message": "No pages with balance sheet keywords found",
                "pages": []
            })

        prompt = f"""
        Analyze the following page snippets from a financial PDF and identify which pages contain a Balance Sheet (Statement of Financial Position).

        Balance sheets typically have:
        - A clear title "Balance Sheet" or "Statement of Financial Position"
        - Three main sections: Assets, Liabilities, and Equity
        - Multiple line items with corresponding amounts
        - Often shows comparative periods (e.g., current year vs previous year)

        Pages to analyze:
        {chr(10).join(pages_info)}

        You MUST respond with ONLY a JSON object, nothing else. No markdown, no explanations, just the JSON:
        {{
            "balance_sheet_pages": [list of page numbers that definitely contain balance sheet data],
            "confidence": "high/medium/low",
            "reasoning": "brief explanation"
        }}
        """

        response = llm.invoke(prompt)

        # Extract JSON from response (handles markdown code blocks)
        response_text = response.content.strip()

        # Try to extract JSON from markdown code blocks
        if "```json" in response_text:
            # Extract content between ```json and ```
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            # Extract content between ``` and ```
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()

        # Remove any leading/trailing whitespace or newlines
        response_text = response_text.strip()

        # Parse JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as je:
            # If still can't parse, return error with actual response for debugging
            return json.dumps({
                "status": "error",
                "message": f"Failed to parse LLM response as JSON: {str(je)}",
                "raw_response": response_text[:500]  # First 500 chars for debugging
            })

        return json.dumps({
            "status": "success",
            "filename": pdf_filename,
            "pages": result.get("balance_sheet_pages", []),
            "confidence": result.get("confidence", "medium"),
            "reasoning": result.get("reasoning", "")
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def check_ade_credits() -> str:
    """
    Checks if Landing AI ADE has sufficient credits/quota available for processing.
    Should be called before attempting any ADE extraction.

    Returns:
        JSON string with credit status and available quota information
    """
    try:
        # Initialize Landing AI ADE client
        client = LandingAIADE()

        # Try to get account/credit information
        # Note: Landing AI ADE might not have a direct credits API endpoint
        # We'll attempt a minimal test to check if the service is accessible

        # Check if we can access the client (basic connectivity test)
        if client:
            return json.dumps({
                "status": "success",
                "message": "Landing AI ADE is accessible",
                "recommendation": "Proceed with extraction. Note: Credit limits are enforced by Landing AI at runtime.",
                "note": "Landing AI ADE will return an error if credits are insufficient during actual processing."
            })
        else:
            return json.dumps({
                "status": "error",
                "message": "Cannot initialize Landing AI ADE client",
                "recommendation": "Check ADE API key configuration"
            })

    except Exception as e:
        error_msg = str(e).lower()

        # Check for common credit/quota related errors
        if any(keyword in error_msg for keyword in ['credit', 'quota', 'limit', 'insufficient', 'balance']):
            return json.dumps({
                "status": "insufficient_credits",
                "message": f"ADE credits may be insufficient: {str(e)}",
                "recommendation": "Please add credits to your Landing AI account before proceeding.",
                "action_required": "Visit Landing AI dashboard to add credits"
            })
        elif 'api key' in error_msg or 'authentication' in error_msg:
            return json.dumps({
                "status": "auth_error",
                "message": f"Authentication issue: {str(e)}",
                "recommendation": "Check your Landing AI API key in .env file"
            })
        else:
            return json.dumps({
                "status": "error",
                "message": f"Error checking ADE credits: {str(e)}",
                "recommendation": "Verify Landing AI ADE configuration and connectivity"
            })


@tool
def extract_balance_sheet_with_ade(pdf_filename: str, page_numbers: str) -> str:
    """
    Extracts balance sheet data from specific pages using Landing AI's ADE (Agentic Document Extraction).
    OPTIMIZED: Only sends the identified pages to ADE, not the entire PDF.

    Args:
        pdf_filename: Name of the PDF file
        page_numbers: JSON string with list of page numbers to extract (e.g., "[22, 23]")

    Returns:
        JSON string with extracted table data
    """
    import tempfile

    try:
        pages = json.loads(page_numbers) if isinstance(page_numbers, str) else page_numbers

        pdf_path = os.path.join(INPUT_FOLDER, pdf_filename)
        if not os.path.exists(pdf_path):
            return json.dumps({"status": "error", "message": f"File not found: {pdf_filename}"})

        # OPTIMIZATION: Extract only balance sheet pages and send to ADE
        # ADE works best with single pages - this avoids processing entire document
        print(f"    📄 Extracting {len(pages)} page(s) from {pdf_filename} for ADE processing")

        # Initialize Landing AI ADE client
        client = LandingAIADE()

        # Process each page separately for best ADE results
        extracted_tables = []

        for page_num in pages:
            try:
                # Open the original PDF
                doc = pymupdf.open(pdf_path)

                # Create a new PDF with only this single page
                single_page_doc = pymupdf.open()

                # Page numbers are 1-indexed in user input, 0-indexed in PyMuPDF
                if 0 < page_num <= len(doc):
                    single_page_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)
                else:
                    doc.close()
                    single_page_doc.close()
                    continue

                # Save to visible temp folder for inspection (NOT deleting after processing)
                base_name = Path(pdf_filename).stem
                temp_pdf_filename = f"{base_name}_page{page_num}_for_ADE.pdf"
                temp_pdf_path = os.path.join(INTERMEDIATE_FILES, temp_pdf_filename)

                single_page_doc.save(temp_pdf_path)
                single_page_doc.close()
                doc.close()

                print(f"      → Saved temp PDF for inspection: {temp_pdf_path}")
                print(f"      → Sending to ADE for processing...")

                # Parse this single page with ADE (optimal for table detection)
                try:
                    parse_result: ParseResponse = client.parse(
                        document=Path(temp_pdf_path),
                        split="page",
                        model=ADE_MODEL
                    )

                    # Save annotated image with bounding boxes
                    annotated_image_path = temp_pdf_path.replace('.pdf', '_annotated.png')
                    if save_annotated_image(parse_result, temp_pdf_path, annotated_image_path):
                        print(f"      → Saved annotated image: {annotated_image_path}")
                except Exception as parse_error:
                    error_msg = str(parse_error).lower()

                    # Check for credit/quota errors
                    if any(keyword in error_msg for keyword in ['credit', 'quota', 'limit', 'insufficient', 'balance', 'exceeded']):
                        # Keep temp file for inspection even on error
                        print(f"      ℹ️  Temp PDF saved for inspection: {temp_pdf_path}")

                        return json.dumps({
                            "status": "insufficient_credits",
                            "message": f"Landing AI ADE credits exhausted: {str(parse_error)}",
                            "recommendation": "Please add credits to your Landing AI account",
                            "pages_attempted": [page_num],
                            "tables": []
                        })
                    else:
                        raise parse_error

                # Extract tables from this page (matching ADE.py successful logic)
                for chunk in parse_result.chunks:
                    if chunk.type == 'table':
                        # Get table content (same as ADE.py)
                        table_content = None
                        if hasattr(chunk, 'markdown') and chunk.markdown:
                            table_content = chunk.markdown
                        elif hasattr(chunk, 'text') and chunk.text:
                            table_content = chunk.text

                        if table_content:
                            print(f"      📊 Found table chunk on page {page_num}")

                            # Validate if this is actually a balance sheet table (same as ADE.py)
                            content_lower = table_content.lower()
                            has_assets = any(keyword in content_lower for keyword in [
                                'assets', 'total assets', 'current assets', 'non-current assets'
                            ])
                            has_liabilities = any(keyword in content_lower for keyword in [
                                'liabilities', 'total liabilities', 'current liabilities',
                                'non-current liabilities', 'payables'
                            ])
                            has_equity = any(keyword in content_lower for keyword in [
                                'equity', 'shareholders equity', 'stockholders equity',
                                'share capital', 'retained earnings', 'reserves'
                            ])
                            has_bs_title = any(keyword in content_lower for keyword in [
                                'balance sheet', 'statement of financial position',
                                'consolidated balance sheet'
                            ])

                            # Validate it's a balance sheet
                            is_balance_sheet = (
                                (has_assets and has_liabilities and has_equity) or
                                (has_bs_title and sum([has_assets, has_liabilities, has_equity]) >= 2)
                            )

                            if is_balance_sheet:
                                print(f"      ✅ Confirmed as Balance Sheet table")

                                # DEBUG: Show raw table content
                                print(f"      🔍 Raw table content (first 500 chars): {table_content[:500]}")

                                # Parse HTML directly — pd.read_html handles colspan correctly
                                try:
                                    import re as _re
                                    dfs = pd.read_html(StringIO(table_content))
                                    if not dfs:
                                        print(f"      ❌ pd.read_html returned no tables")
                                        continue

                                    df = dfs[0]

                                    # Coalesce duplicate columns caused by colspan.
                                    # pd.read_html suffixes repeated headers as "Header", "Header.1", etc.
                                    # We merge them by taking the first non-NaN value per row.
                                    coalesced = {}
                                    order = []
                                    for col in df.columns:
                                        base = _re.sub(r'\.\d+$', '', str(col))
                                        if base not in coalesced:
                                            coalesced[base] = df[col].copy()
                                            order.append(base)
                                        else:
                                            coalesced[base] = coalesced[base].combine_first(df[col])

                                    df = pd.DataFrame({k: coalesced[k] for k in order})

                                    print(f"      🔍 Columns after coalescing: {list(df.columns)}")
                                    print(f"      🔍 Shape: {df.shape}")

                                    # Serialise as list-of-lists (header row first) for JSON handoff
                                    data = [list(df.columns)] + df.fillna('').astype(str).values.tolist()

                                    print(f"      🔍 Final parsed data rows: {len(data)}")
                                    print(f"      🔍 Header row: {data[0]}")
                                    print(f"      🔍 Last row:   {data[-1]}")

                                    if len(data) > 1:
                                        extracted_tables.append({
                                            "page": page_num,
                                            "data": data
                                        })
                                        print(f"      ✅ Extracted table with {len(data)} rows on page {page_num}")
                                    else:
                                        print(f"      ❌ Table too small after parsing")

                                except Exception as parse_err:
                                    print(f"      ❌ pd.read_html failed: {parse_err}")
                            else:
                                print(f"      ⏭️  Table doesn't match balance sheet criteria (Assets:{has_assets}, Liabilities:{has_liabilities}, Equity:{has_equity})")

                # Keep temp file for inspection (NOT deleting)
                print(f"      ℹ️  Temp PDF kept at: {temp_pdf_path}")

            except Exception as e:
                print(f"      ⚠️ Error processing page {page_num}: {str(e)}")
                continue

        if not extracted_tables:
            return json.dumps({
                "status": "no_tables",
                "message": f"No tables found on specified pages {pages}",
                "tables": []
            })

        return json.dumps({
            "status": "success",
            "filename": pdf_filename,
            "pages_processed": pages,
            "tables_found": len(extracted_tables),
            "tables": extracted_tables
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def parse_and_save_to_excel(pdf_filename: str, extracted_data: str) -> str:
    """
    Parses extracted balance sheet data and saves it to Excel format with structural integrity.
    Handles multiline cells, splits merged text+numbers, and preserves table structure.

    Args:
        pdf_filename: Original PDF filename (used for naming output file)
        extracted_data: JSON string with extracted table data from extract_balance_sheet_with_ade

    Returns:
        JSON string with save status and output file path
    """
    try:
        data = json.loads(extracted_data)

        if data.get("status") != "success":
            return extracted_data  # Return error as is

        tables = data.get("tables", [])
        if not tables:
            return json.dumps({"status": "error", "message": "No tables to save"})

        # Create output filename
        base_name = Path(pdf_filename).stem
        output_filename = os.path.join(OUTPUT_FOLDER, f"{base_name}_balance_sheet.xlsx")

        # Helper function to expand multiline cells
        def expand_multiline_cells(df: pd.DataFrame) -> pd.DataFrame:
            has_newlines = any(df[col].astype(str).str.contains('\n').any() for col in df.columns)
            if not has_newlines:
                return df

            expanded_data = []
            for idx, row in df.iterrows():
                split_row = []
                max_lines = 1

                for cell in row:
                    if pd.notna(cell) and '\n' in str(cell):
                        parts = str(cell).split('\n')
                        split_row.append(parts)
                        max_lines = max(max_lines, len(parts))
                    else:
                        split_row.append([cell])

                for line_idx in range(max_lines):
                    new_row = []
                    for cell_parts in split_row:
                        if line_idx < len(cell_parts):
                            new_row.append(cell_parts[line_idx])
                        else:
                            new_row.append(None)
                    expanded_data.append(new_row)

            expanded_df = pd.DataFrame(expanded_data, columns=df.columns)
            expanded_df = expanded_df.replace('', None).dropna(how='all').reset_index(drop=True)
            return expanded_df

        # Helper function to split text and numbers
        def split_text_and_numbers(text: str) -> list:
            import re
            if pd.isna(text) or text is None:
                return [text]

            text = str(text).strip()
            if re.match(r'^[-\(\)0-9,.\s]*$', text):
                return [text]

            pattern = r'^(.+?)\s+([-\(\)]?\d+(?:[,\.]\d+)*(?:\s+[-\(\)]?\d+(?:[,\.]\d+)*)*)$'
            match = re.match(pattern, text)

            if match:
                text_part = match.group(1).strip()
                numbers_part = match.group(2).strip()
                number_parts = re.findall(r'[-\(\)]?\d+(?:[,\.]\d+)*', numbers_part)

                if number_parts and not re.search(r'\d{2,}$', text_part):
                    return [text_part] + number_parts

            return [text]

        # Helper function to split merged columns
        def split_merged_columns(df: pd.DataFrame) -> pd.DataFrame:
            if len(df) == 0:
                return df

            first_col = df.columns[0]
            sample_size = min(5, len(df))

            needs_splitting = False
            for i in range(sample_size):
                cell_value = str(df.iloc[i, 0]) if pd.notna(df.iloc[i, 0]) else ""
                if cell_value:
                    parts = split_text_and_numbers(cell_value)
                    if len(parts) > 1:
                        needs_splitting = True
                        break

            if not needs_splitting:
                return df

            new_rows = []
            max_parts = 1

            for idx, row in df.iterrows():
                cell_value = row.iloc[0]
                parts = split_text_and_numbers(cell_value)
                max_parts = max(max_parts, len(parts))
                new_row = parts + list(row.iloc[1:])
                new_rows.append(new_row)

            if max_parts > 1:
                new_columns = ['Description'] + [f'Value_{i}' for i in range(1, max_parts)]
                new_columns += list(df.columns[1:])
                return pd.DataFrame(new_rows, columns=new_columns)

            return df

        # Process and save tables
        with pd.ExcelWriter(output_filename, engine='openpyxl') as writer:
            saved_count = 0

            for table_info in tables:
                table_data = table_info.get("data", [])
                if not table_data or len(table_data) < 2:
                    continue

                # Convert to DataFrame
                df = pd.DataFrame(table_data)
                df = df.replace('', None).replace(r'^\s*$', None, regex=True)
                df = df.dropna(how='all').reset_index(drop=True)

                if len(df) == 0:
                    continue

                # Find header row
                header_row_idx = 0
                max_non_null = 0
                for i in range(min(3, len(df))):
                    non_null_count = df.iloc[i].notna().sum()
                    if non_null_count > max_non_null:
                        max_non_null = non_null_count
                        header_row_idx = i

                # Extract and clean headers
                headers = df.iloc[header_row_idx].tolist()
                clean_headers = []
                for i, header in enumerate(headers):
                    if header is None or pd.isna(header) or str(header).strip() == '':
                        clean_headers.append(f"Column_{i+1}")
                    else:
                        base_header = str(header).strip()
                        if '\n' in base_header:
                            header_parts = [p.strip() for p in base_header.split('\n') if p.strip()]
                            base_header = header_parts[0] if header_parts else f"Column_{i+1}"

                        if base_header in clean_headers:
                            count = 1
                            while f"{base_header}_{count}" in clean_headers:
                                count += 1
                            clean_headers.append(f"{base_header}_{count}")
                        else:
                            clean_headers.append(base_header)

                df.columns = clean_headers
                df = df.iloc[header_row_idx + 1:].copy().reset_index(drop=True)
                df = df.dropna(how='all')

                # Apply transformations
                df = expand_multiline_cells(df)
                df = split_merged_columns(df)

                if len(df) > 0 and len(df.columns) > 0:
                    df['Source Document'] = Path(pdf_filename).name
                    df['Page Number'] = table_info.get('page', '')
                    sheet_name = f"Page{table_info.get('page', saved_count+1)}"
                    sheet_name = sheet_name[:31]
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    saved_count += 1

        if saved_count > 0:
            return json.dumps({
                "status": "success",
                "message": f"Successfully saved {saved_count} balance sheet table(s)",
                "output_file": output_filename,
                "tables_saved": saved_count
            })
        else:
            return json.dumps({
                "status": "error",
                "message": "No valid tables to save"
            })

    except Exception as e:
        import traceback
        return json.dumps({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        })


@tool
def write_extraction_manifest() -> str:
    """
    Scans the output folders and writes a manifest JSON summarising everything
    the extraction run produced.  This file is the handoff artifact that the
    Evaluation Agent reads to know what to evaluate.

    Returns:
        JSON string with the manifest path and its contents.
    """
    import re
    from datetime import datetime

    try:
        excel_files = glob.glob(os.path.join(OUTPUT_FOLDER, "*.xlsx"))
        source_pdfs = glob.glob(os.path.join(INPUT_FOLDER, "*.pdf"))
        temp_pdfs = glob.glob(os.path.join(INTERMEDIATE_FILES, "*.pdf"))

        # Parse which pages were extracted from the temp PDF filenames
        # Format: {base}_page{N}_for_ADE.pdf
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
            "timestamp": datetime.now().isoformat(),
            "input_folder": INPUT_FOLDER,
            "output_folder": OUTPUT_FOLDER,
            "temp_folder": INTERMEDIATE_FILES,
            "source_pdfs": [os.path.basename(p) for p in source_pdfs],
            "excel_outputs": [os.path.basename(e) for e in excel_files],
            "pages_extracted": pages_by_source,
        }

        manifest_path = os.path.join(INTERMEDIATE_FILES, "extraction_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        print(f"    📋 Manifest written to {manifest_path}")
        return json.dumps({
            "status": "success",
            "manifest_path": manifest_path,
            "manifest": manifest,
        })

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


# ============================================================================
# AGENT SETUP
# ============================================================================

# Define all tools
tools = [
    list_pdf_files_in_folder,
    extract_text_from_pdf_pages,
    identify_balance_sheet_pages,
    check_ade_credits,
    extract_balance_sheet_with_ade,
    parse_and_save_to_excel,
    write_extraction_manifest,
]

# Create LLM with function calling (using Claude)
llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)
llm_with_tools = llm.bind_tools(tools)


def run_agent(task: str, max_iterations: int = 15):
    """
    Runs the agent to complete the given task using ReAct-style reasoning.

    Args:
        task: The task description for the agent
        max_iterations: Maximum number of iterations before stopping
    """
    print("="*70)
    print("🤖 BALANCE SHEET EXTRACTION AGENT")
    print("="*70)
    print(f"Task: {task}\n")

    # System prompt for the agent
    system_prompt = """You are a specialized AI agent for extracting balance sheets from financial PDFs.

Your task is to:
1. Check if Landing AI ADE has sufficient credits BEFORE starting extraction
2. List PDF files in the input folder
3. For each PDF, extract text from pages to identify which pages contain balance sheets
4. Use the LLM to identify the specific page numbers with balance sheet data
5. Extract balance sheet tables from those pages using Landing AI's ADE (one page at a time)
6. Parse and save the extracted data to Excel format in the output folder

CRITICAL REQUIREMENTS:
- ALWAYS check ADE credits FIRST using check_ade_credits before any extraction
- If credits are insufficient, STOP and inform the user to add credits
- Only proceed with extraction if credits are available
- ADE works best with single pages - each identified page is sent separately
- Always verify that balance sheets are actually present before attempting extraction
- Ensure data integrity is maintained when converting to Excel
- Process one PDF completely before moving to the next

Available tools:
- list_pdf_files_in_folder: Get list of PDFs to process
- extract_text_from_pdf_pages: Get text snippets from all pages
- identify_balance_sheet_pages: Use LLM to identify which pages have balance sheets
- check_ade_credits: CHECK THIS FIRST - Verify Landing AI ADE credits are available
- extract_balance_sheet_with_ade: Extract tables using Landing AI ADE (one page at a time)
- parse_and_save_to_excel: Save extracted data to Excel with proper formatting
- write_extraction_manifest: CALL THIS LAST — writes the handoff JSON for the Evaluation Agent

Work systematically through each PDF and provide a summary when complete.

FINAL STEP: After all PDFs have been processed and saved to Excel, ALWAYS call
write_extraction_manifest() as the very last tool call.  This writes the handoff
artifact that the Evaluation Agent needs to start its work."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=task)
    ]

    iterations = 0

    while iterations < max_iterations:
        iterations += 1
        print(f"\n--- Iteration {iterations} ---")

        # Get agent response
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        # Check if agent wants to use tools
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                print(f"🔧 Tool: {tool_name}")
                print(f"📥 Args: {json.dumps(tool_args, indent=2)}")

                # Find and execute the tool
                tool_func = next((t for t in tools if t.name == tool_name), None)
                if tool_func:
                    try:
                        observation = tool_func.invoke(tool_args)
                        print(f"📤 Output: {observation[:500]}..." if len(str(observation)) > 500 else f"📤 Output: {observation}")

                        # Add tool result to messages
                        from langchain_core.messages import ToolMessage
                        messages.append(ToolMessage(
                            content=observation,
                            tool_call_id=tool_call["id"]
                        ))
                    except Exception as e:
                        error_msg = f"Error executing tool: {str(e)}"
                        print(f"❌ {error_msg}")
                        messages.append(ToolMessage(
                            content=error_msg,
                            tool_call_id=tool_call["id"]
                        ))
                else:
                    error_msg = f"Error: Tool {tool_name} not found"
                    print(f"❌ {error_msg}")
                    messages.append(ToolMessage(
                        content=error_msg,
                        tool_call_id=tool_call["id"]
                    ))
        else:
            # Agent finished - no more tool calls
            print(f"\n✅ Agent finished!")
            print(f"💬 Final response: {response.content}")
            return {"output": response.content}

    print(f"\n⚠️ Max iterations ({max_iterations}) reached")
    return {"output": "Max iterations reached without completion"}


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    task = """
    Please process all PDF files in the current folder and extract balance sheet data.

    For each PDF:
    0. List PDF files in the input folder
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

    result = run_agent(task, max_iterations=25)

    print("\n" + "="*70)
    print("🎉 PROCESSING COMPLETE")
    print("="*70)
