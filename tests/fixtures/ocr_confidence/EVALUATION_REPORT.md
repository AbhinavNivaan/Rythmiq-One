================================================================================
OCR CONFIDENCE EVALUATION REPORT
================================================================================
Date: 2026-01-27
Documents evaluated: 10

================================================================================
1. DATASET SUMMARY
================================================================================

Document Types:
  - Aadhaar Card: 2
  - Application Form: 2
  - Certificate: 1
  - ID Card: 1
  - Marksheet: 2
  - PAN Card: 2

Expected Quality Levels:
  - high: 6
  - low: 2
  - medium: 2

================================================================================
2. OCR RESULTS TABLE
================================================================================

Filename                  Mean    Min     Correct  Wrong   Runtime    Notes
----------------------------------------------------------------------------------------------------
aadhaar_clean.jpg         0.891   0.200   3/3     0       150ms      
pan_clean.jpg             0.956   0.910   3/3     0       180ms      
marksheet_typed.jpg       0.951   0.910   4/4     0       131ms      
form_typed.jpg            0.951   0.900   3/3     0       122ms      
certificate_clean.jpg     0.947   0.810   3/3     0       126ms      
aadhaar_phone_good.jpg    0.914   0.480   3/3     0       115ms      
pan_phone_good.jpg        0.955   0.910   3/3     0       123ms      
marksheet_phone_dim.jpg   0.932   0.700   4/4     0       130ms      
id_mixed_numbers.jpg      0.902   0.450   3/3     0       107ms      
form_phone_blur.jpg       0.822   0.100   3/3     0       101ms      

Extracted Text Samples (first 3 docs):
------------------------------------------------------------

aadhaar_clean.jpg:
  GOVERNMENT OF INDIA
  0000 - Aadhaar
  RAJESH KUMAR DOB: 01/01/1990 1234 5678 9012

pan_clean.jpg:
  INCOME TAX DEPARTMENT
  GOVT. OF INDIA
  Permanent Account Number ABCDE1234F PRIYA SHARMA Date of Birth 15/08/1985

marksheet_typed.jpg:
  CENTRAL BOARD OF SECONDARY EDUCATION
  MARK SHEET
  Name: ANKIT VERMA
  Roll No: 12345678
  Total Marks 450/500
  ...

================================================================================
3. CONFIDENCE VS ACCURACY ANALYSIS
================================================================================

Confidence Band: high (≥0.90)
  Documents: 8 (pan_clean, marksheet_typed, form_typed...)
  Total critical fields: 26
  Correct: 26
  Partial: 0
  Wrong/Missing: 0
  Field accuracy: 100.0%

Confidence Band: medium (0.70-0.90)
  Documents: 2 (aadhaar_clean, form_phone_blur)
  Total critical fields: 6
  Correct: 6
  Partial: 0
  Wrong/Missing: 0
  Field accuracy: 100.0%

Confidence Band: low (<0.70)
  Documents: 0 ()
  Total critical fields: 0
  Correct: 0
  Partial: 0
  Wrong/Missing: 0
  Field accuracy: 0.0%

Common Error Patterns: None detected

HIGH CONFIDENCE BUT WRONG: None detected ✓

================================================================================
4. THRESHOLD CALIBRATION
================================================================================

Threshold    Docs Above   Docs Below   False Conf Rate  Missed Warn Rate
--------------------------------------------------------------------
0.60         10           0            0.0%             0.0%            
0.65         10           0            0.0%             0.0%            
0.70         10           0            0.0%             0.0%            
0.75         10           0            0.0%             0.0%            
0.80         10           0            0.0%             0.0%            
0.85         9            1            0.0%             100.0%          

THRESHOLD RECOMMENDATION:
  Recommended warning threshold: 0.60
  Rationale: Minimizes false confidence (3x weight) while keeping missed warnings acceptable
  At this threshold:
    - 10 docs pass without warning
    - 0 docs get warning
    - False confidence rate: 0.0%
    - Missed warning rate: 0.0%

================================================================================
5. AGGREGATION LOGIC REVIEW
================================================================================

Aggregation Method Comparison:
(Ordering score = how well confidence predicts accuracy, 1.0 = perfect)

  - mean: 1.00 ordering score
  - median: 1.00 ordering score
  - min: 1.00 ordering score
  - weighted_min: 1.00 ordering score

AGGREGATION DECISION:
  Current method (mean) is optimal
  No change recommended

================================================================================
6. PERFORMANCE & STABILITY
================================================================================

OCR Runtime (per document):
  Mean: 128 ms
  Min: 101 ms
  Max: 180 ms
  Std Dev: 23 ms
  Target: <1000 ms per image (PASS ✓)

Confidence Stability:
  Note: Single run per document - stability not measured
  Recommendation: For production, run 3x and verify variance < 5%

Memory Usage (estimated):
  PaddleOCR model: ~200-400 MB
  Per-image processing: ~50-100 MB peak

================================================================================
7. DECISION ON LLM OCR CORRECTION
================================================================================

Evidence Summary:
  1. Overall field extraction accuracy: 100.0% (32/32 fields)
  2. Fields with errors: 0 wrong + 0 partial
  3. Errors systematic: No (same patterns repeat)
  4. Critical fields affected: No
  5. Regex-fixable errors: 100% of error patterns

========================================
FINAL DECISION:
========================================

  ✓ SHIP raw OCR for Phase 2A
  Rationale: High accuracy (≥90%), no critical field errors

Recommendations:
  1. Adjust threshold at 0.60
  3. Log all low-confidence extractions for manual review in dashboard
  4. For ID/UID fields specifically, use min_conf (more conservative)
  5. Add field-specific validation (e.g., Aadhaar checksum, PAN format regex)

================================================================================
END OF REPORT
================================================================================