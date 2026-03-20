# Evaluation Framework for Balance Sheet Extraction Agent

## 1. Core KPIs (Key Performance Indicators)

### Accuracy Metrics

#### 1.1 Field-Level Accuracy
**Definition**: Percentage of individual values extracted correctly
```
Field Accuracy = (Correct Values / Total Values) × 100
```
- **Target**: ≥95%
- **How to measure**: Manual comparison of extracted Excel vs source PDF
- **Critical fields**: Total Assets, Total Liabilities, Total Equity, major line items

#### 1.2 Structural Accuracy
**Definition**: Percentage of tables with correct structure preserved
```
Structural Accuracy = (Tables with Correct Structure / Total Tables) × 100
```
- **Target**: ≥90%
- **What to check**:
  - Headers aligned with data columns
  - Parent-child relationships (e.g., "Current Assets" → subcategories)
  - Hierarchical indentation preserved
  - No merged text+number cells

#### 1.3 Balance Sheet Validation Rate
**Definition**: Percentage of extracted balance sheets that pass accounting rules
```
Validation Rate = (Sheets Passing Validation / Total Sheets) × 100

Validation Rules:
- Assets = Liabilities + Equity
- Total Assets = Sum of line items
- Subtotals match their components
```
- **Target**: 100% (must pass basic accounting)

### Completeness Metrics

#### 1.4 Data Completeness
**Definition**: Percentage of expected fields actually extracted
```
Completeness = (Extracted Fields / Expected Fields) × 100
```
- **Target**: ≥98%
- **Expected fields**: All line items visible in PDF table

#### 1.5 Page Detection Accuracy
**Definition**: How well the agent identifies balance sheet pages
```
Precision = True Positives / (True Positives + False Positives)
Recall = True Positives / (True Positives + False Negatives)
F1 Score = 2 × (Precision × Recall) / (Precision + Recall)
```
- **Target**: Precision ≥95%, Recall ≥98%

### Efficiency Metrics

#### 1.6 Processing Cost per Document
**Definition**: Average ADE credits/API cost per successfully processed PDF
```
Cost per Doc = Total ADE Credits Used / Documents Processed
```
- **Target**: Minimize while maintaining accuracy
- **Track**: Credits per page, false page detections (wasted credits)

#### 1.7 Processing Time
```
Time per Document = Total Processing Time / Documents Processed
```
- **Target**: <2 minutes per document (depends on length)
- **Breakdown**: Page identification time, ADE processing time, Excel conversion time

#### 1.8 Credit Efficiency
**Definition**: Percentage of ADE credits spent on actual balance sheet pages
```
Credit Efficiency = (Credits on Valid Pages / Total Credits) × 100
```
- **Target**: ≥85% (minimize false positives in page detection)

### Reliability Metrics

#### 1.9 Success Rate
```
Success Rate = (Successful Extractions / Total Attempts) × 100
```
- **Target**: ≥95%
- **Failure reasons**: Credit exhaustion, parsing errors, no balance sheet found

#### 1.10 Error Rate by Type
Track different failure modes:
- **Page detection failures**: Balance sheet exists but not detected
- **ADE parsing failures**: ADE returns error or poor quality
- **Excel conversion failures**: Data extraction works but Excel save fails
- **Validation failures**: Extract completes but data doesn't balance

---

## 2. OKRs (Objectives and Key Results)

### Q1 2026 - Production Readiness

**Objective 1: Achieve Production-Grade Accuracy**
- **KR1**: Reach 98% field-level accuracy on 100+ test documents
- **KR2**: Achieve 95% structural accuracy across diverse PDF formats
- **KR3**: 100% of extractions pass basic accounting validation (Assets = Liabilities + Equity)
- **KR4**: Reduce false positive page detection to <5%

**Objective 2: Optimize Cost Efficiency**
- **KR1**: Reduce average processing cost to <$0.50 per document
- **KR2**: Improve credit efficiency to 90% (only 10% wasted on wrong pages)
- **KR3**: Reduce processing time to <90 seconds per document
- **KR4**: Zero credit exhaustion incidents through proactive monitoring

**Objective 3: Build Robust Evaluation Pipeline**
- **KR1**: Create test dataset of 50 diverse balance sheets with ground truth
- **KR2**: Implement automated comparison tool for Excel vs PDF
- **KR3**: Set up dashboard tracking all KPIs in real-time
- **KR4**: Document 20 edge cases and handling strategies

---

## 3. Evaluation Methodology

### 3.1 Test Dataset Requirements

**Diversity Dimensions**:
- **Document sources**: 10+ different companies/organizations
- **Formats**: Single-page, multi-page, consolidated, standalone
- **Layouts**: Traditional two-column, multi-period comparisons, complex hierarchies
- **Complexity levels**:
  - Simple: <30 line items, 2 columns
  - Medium: 30-60 line items, 3-4 columns
  - Complex: >60 line items, 5+ columns, nested categories

**Ground Truth Creation**:
1. Manually extract balance sheet data to Excel (gold standard)
2. Document expected structure (headers, hierarchy, subtotals)
3. Note any special characteristics (merged cells, footnotes, etc.)
4. Store PDF + ground truth Excel + metadata JSON

### 3.2 Automated Comparison Tool

```python
# Pseudo-code for comparison tool
def evaluate_extraction(ground_truth_excel, extracted_excel):
    """
    Compares extracted output against ground truth
    Returns detailed accuracy metrics
    """
    metrics = {
        'field_accuracy': compare_cell_values(ground_truth, extracted),
        'structural_accuracy': compare_table_structure(ground_truth, extracted),
        'completeness': check_missing_fields(ground_truth, extracted),
        'balance_validation': validate_accounting_rules(extracted),
        'differences': list_all_differences(ground_truth, extracted)
    }
    return metrics
```

### 3.3 Evaluation Process

**Weekly Regression Testing**:
1. Run agent on entire test dataset (50 documents)
2. Automatically compare outputs vs ground truth
3. Generate accuracy report with KPI dashboard
4. Flag any regressions or new failure modes
5. Update test dataset with any new edge cases discovered

**Manual Spot Checks**:
- Review 10% of production runs manually
- Deep dive into any documents with accuracy <90%
- Validate that automated metrics align with human judgment

---

## 4. Practical Implementation

### 4.1 Quick Start - Minimal Viable Evaluation

**Step 1: Create Mini Test Set (5 documents)**
- 1 simple balance sheet
- 1 multi-page balance sheet
- 1 complex/consolidated statement
- 1 unusual format
- 1 known failure case

**Step 2: Manual Baseline Evaluation**
```
For each test document:
1. Run agent extraction
2. Open PDF and extracted Excel side by side
3. Check 10 random values - are they correct?
4. Check structure - are headers/hierarchies preserved?
5. Run accounting check - does it balance?
6. Record: Pass/Fail + specific issues found
```

**Step 3: Track These 5 Core Metrics**
1. Overall success rate (did it extract anything?)
2. Field accuracy (spot check 10 values per doc)
3. Balance validation (Assets = Liabilities + Equity)
4. Processing cost (ADE credits used)
5. Processing time

### 4.2 Full Evaluation Pipeline

I can help you build:
1. **Test dataset generator**: Script to organize test PDFs + ground truth
2. **Automated comparison tool**: Excel-to-Excel diff with accuracy scoring
3. **Dashboard**: Real-time KPI tracking (can use simple Python/Streamlit)
4. **Regression suite**: Run full test set on every code change

---

## 5. Benchmark Targets (Industry Context)

**Document Extraction Standards**:
- **Good**: 85-90% accuracy, requires human review
- **Very Good**: 90-95% accuracy, spot checks only
- **Excellent**: 95-98% accuracy, minimal human intervention
- **Best-in-class**: >98% accuracy, fully automated

**Your Agent's Position**:
- For **structured financial tables** (like balance sheets), target should be 95%+
- Balance sheets have validation rules (must balance), so aim for 100% validation pass
- Complex nested tables are harder - 90%+ structural accuracy is very good

---

## 6. Continuous Improvement Loop

```
1. Run agent on new document
2. Compare output vs expected (manual or automated)
3. If accuracy < target:
   - Categorize failure type (detection, extraction, parsing)
   - Add to test dataset
   - Adjust prompts/logic
   - Re-test
4. Update KPI dashboard
5. Review trends weekly
```

---

## Next Steps

**Immediate Actions**:
- [ ] Select 5-10 test documents with ground truth
- [ ] Run current agent and manually score accuracy
- [ ] Establish baseline KPIs
- [ ] Identify top 3 failure modes
- [ ] Set realistic targets for next version

**Would you like me to help you build**:
1. Automated Excel comparison tool?
2. Test dataset structure and evaluation script?
3. KPI tracking dashboard?
4. Specific accuracy measurement for your current extractions?
