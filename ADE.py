#pip install pymupdf pandas python-dotenv pillow ipython landingai-ade openpyxl lxml openpyxl

# General imports
import os
import json
import pymupdf
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from io import StringIO


# Imports specific to Agentic Document Extraction
from landingai_ade import LandingAIADE
from landingai_ade.types import ParseResponse, ExtractResponse

# Load environment variables from .env
_ = load_dotenv(override=True)

# --- 1. Setup and Parsing ---
# Initialize the client
client = LandingAIADE()
print("Authenticated client initialized")

from helper import print_document, draw_bounding_boxes, draw_bounding_boxes_2
from helper import create_cropped_chunk_images

print_document("/Users/pranayagarwal/Desktop/Financial Statements Extractor/temp_ade_pages/Alliander-Half-Year-Report-2025-FULL_page22_for_ADE.pdf")

# Specify the file path to the document - INPUT
document_path = Path("/Users/pranayagarwal/Desktop/Financial Statements Extractor/temp_ade_pages/Alliander-Half-Year-Report-2025-FULL_page22_for_ADE.pdf")

print("⚡ Calling API to parse document...")

# Parse the document using the Parse() API
parse_result: ParseResponse = client.parse(
    document=document_path,
    split = "page",
    model="dpt-2-latest"
)

print(f"✅ Parsing completed.")
print(f"job_id: {parse_result.metadata.job_id}")
print(f"Filename: {parse_result.metadata.filename}")
print(f"Total time (ms): {parse_result.metadata.duration_ms}")
print(f"Total pages: {len(parse_result.splits)}")
print(f"Total markdown characters: {len(parse_result.markdown)}")
print(f"Total chunks: {len(parse_result.chunks)}")

# Create and view an annotated version
draw_bounding_boxes(parse_result, document_path)

# Save Markdown output (useful if you plan to run extract on the Markdown)
with open("output.md", "w", encoding="utf-8") as f:
    f.write(parse_result.markdown)

# How many chunks of each type?
counts = {}

for chunk in parse_result.model_dump()["chunks"]:
    t = chunk["type"]
    counts[t] = counts.get(t, 0) + 1

print(f"Total Chunk Types: '{counts}'")

# --- DEBUG: Inspect chunk attributes ---
print("\n🔍 Inspecting first few chunks to understand structure:")
for i, chunk in enumerate(parse_result.chunks[:5]):
    print(f"\nChunk {i}:")
    print(f"  Type: {chunk.type}")
    print(f"  Available attributes: {[attr for attr in dir(chunk) if not attr.startswith('_')]}")
    if hasattr(chunk, 'text'):
        print(f"  Text preview: {chunk.text[:100] if chunk.text else 'None'}...")
    if hasattr(chunk, 'markdown'):
        print(f"  Markdown preview: {chunk.markdown[:100] if chunk.markdown else 'None'}...")

# --- 2. Identify and Filter Balance Sheet Tables ---
balance_sheet_data = []
current_section = None

# Iterate through the structured chunks from the response
for chunk in parse_result.chunks:
    # Track the current section from text chunks (headers/titles)
    if chunk.type == 'text' and hasattr(chunk, 'text') and chunk.text:
        text_lower = chunk.text.strip().lower()
        # Look for section headers
        if any(keyword in text_lower for keyword in ['balance sheet', 'statement of financial position']):
            current_section = 'balance sheet'
            print(f"Found section header: {chunk.text.strip()}")
    
    # Check if the chunk is a table
    if chunk.type == 'table':
        # Get the table content - check which attribute contains the data
        table_content = None
        
        if hasattr(chunk, 'markdown') and chunk.markdown:
            table_content = chunk.markdown
        elif hasattr(chunk, 'text') and chunk.text:
            table_content = chunk.text
        
        if table_content:
            print(f"\n📊 Found table chunk:")
            print(f"Content preview: {table_content}...")
            
            # Try to determine if this is a balance sheet table by looking at content
            content_lower = table_content.lower()

            # Check for all three required components
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

            # Additional balance sheet identifiers (optional but helpful)
            has_bs_title = any(keyword in content_lower for keyword in [
                'balance sheet', 'statement of financial position',
                'statement of financial condition', 'consolidated balance sheet'
            ])

            # A table is a balance sheet if it has ALL three components
            # OR if it has the title plus at least 2 of the 3 components
            is_balance_sheet = (
                (has_assets and has_liabilities and has_equity) or
                (has_bs_title and sum([has_assets, has_liabilities, has_equity]) >= 2)
            )

            if is_balance_sheet:
                print(f"  ✅ Identified as Balance Sheet")
                print(f"    - Has Assets: {has_assets}")
                print(f"    - Has Liabilities: {has_liabilities}")
                print(f"    - Has Equity: {has_equity}")
            else:
                print(f"  ⏭️ Not a balance sheet (missing required sections)")
            
## PK Works until here. Conversion of markdown to dataframe needs to be more robust.

            if is_balance_sheet or current_section == 'balance sheet':
                try:
                    df = None
                    
                    # Try reading as HTML first (if it's HTML table)
                    if '<table' in table_content.lower():
                        dfs = pd.read_html(StringIO(table_content))
                        df = dfs[0] if dfs else None
                    else:
                        # Parse markdown table
                        lines = table_content.strip().split('\n')
                        
                        # Remove separator lines (more robust pattern)
                        lines = [line for line in lines if not (
                            line.strip().startswith('|') and 
                            set(line.replace('|', '').replace('-', '').replace(':', '').strip()) == set()
                        )]
                        
                        # Parse pipe-separated values
                        data = []
                        for line in lines:
                            if '|' in line:
                                # Split by | and clean up
                                row = [cell.strip() for cell in line.split('|')]
                                # Remove empty first/last elements from split
                                row = [cell for cell in row if cell or cell == '0']
                                if row:  # Only add non-empty rows
                                    data.append(row)
                        
                        if data and len(data) > 1:
                            # Find the header row (usually has date columns)
                            header_idx = 0
                            for i, row in enumerate(data):
                                if any('2024' in str(cell) or '2025' in str(cell) for cell in row):
                                    header_idx = i
                                    break
                            
                            headers = data[header_idx]
                            body = data[header_idx + 1:]
                            
                            # Ensure all rows have same length as headers
                            max_cols = len(headers)
                            body = [row + [''] * (max_cols - len(row)) if len(row) < max_cols else row[:max_cols] for row in body]
                            
                            df = pd.DataFrame(body, columns=headers)
                    
                    if df is not None:
                        # Clean the DataFrame
                        # 1. Remove completely empty rows
                        df = df.dropna(how='all')
                        
                        # 2. Remove rows where first column is empty (usually formatting artifacts)
                        if len(df.columns) > 0:
                            df = df[df.iloc[:, 0].notna() & (df.iloc[:, 0] != '')]
                        
                        # 3. Convert numeric columns (skip first column which is labels)
                        for col in df.columns[1:]:
                            df[col] = df[col].apply(lambda x: pd.to_numeric(
                                str(x).replace(',', '').replace('€', '').strip(), 
                                errors='ignore'
                            ))
                        
                        # 4. Reset index
                        df = df.reset_index(drop=True)
                        
                        balance_sheet_data.append(df)
                        print(f"  ✅ Successfully parsed table")
                        print(f"  Shape: {df.shape}")
                        print(f"  Columns: {list(df.columns)}")
                    
                except Exception as e:
                    print(f"  ❌ Could not convert table to DataFrame: {e}")
                    import traceback
                    traceback.print_exc()

            # --- 3. Consolidate and Save to Excel ---
            if balance_sheet_data:
                # Save each table to a separate sheet OR combine if they have same structure
                output_excel_filename = "balance_sheet_extracted.xlsx"
                
                with pd.ExcelWriter(output_excel_filename, engine='openpyxl') as writer:
                    if len(balance_sheet_data) == 1:
                        # Single table - save to default sheet
                        balance_sheet_data[0].to_excel(writer, sheet_name='Balance Sheet', index=False)
                    else:
                        # Multiple tables - check if they can be combined
                        same_columns = all(list(df.columns) == list(balance_sheet_data[0].columns) 
                                        for df in balance_sheet_data)
                        
                        if same_columns:
                            # Combine into one sheet
                            combined_df = pd.concat(balance_sheet_data, ignore_index=True)
                            combined_df.to_excel(writer, sheet_name='Balance Sheet', index=False)
                        else:
                            # Save to separate sheets
                            for i, df in enumerate(balance_sheet_data):
                                sheet_name = f'Balance Sheet {i+1}'
                                df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                print(f"\n✅ Successfully extracted {len(balance_sheet_data)} table(s) and saved to {output_excel_filename}")
            else:
                print("\n⚠️ No balance sheet data was found or extracted.")