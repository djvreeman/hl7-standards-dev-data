# QA Script Fixes Summary

## Issues Found and Fixed

### 1. Status Distribution Percentages (73.9% instead of 100%)

**Issue**: The QA script was reporting an error that status distribution percentages don't sum to 100%.

**Root Cause**: The status distribution table intentionally excludes "Unresolved" and "Resolved (not applied)" statuses (see line 1351 in `applied-issues-analyze.py`). These are inferred statuses, not real workflow statuses, so they're excluded from the table. The percentages correctly sum to the percentage of issues that have real workflow statuses.

**Fix**: Changed the check from an error to an informational message. The script now:
- Calculates what percentage the shown statuses represent
- Verifies that percentages match the counts (within rounding)
- Notes that the table excludes inferred statuses

**Status**: ✅ Fixed - Changed from error to info message

### 2. Applied Count Mismatch (Report=23946, Data=2475)

**Issue**: The QA script was reading the wrong column from the report table.

**Root Cause**: The regex pattern was matching the 5th column (Done) instead of the 4th column (Applied) in the "Issues by Category" table. The table structure is:
- Column 1: New
- Column 2: Deciding (Backlog)
- Column 3: Doing
- Column 4: Applied ← Should read this
- Column 5: Done ← Was reading this

**Fix**: Updated the regex to:
- First find the "Issues by Category" section
- Extract the section text
- Match all 5 columns explicitly
- Use the 4th column (Applied) for comparison

**Status**: ✅ Fixed - Now correctly reads the Applied column

### 3. Resolution Count Mismatch (Calculated=2475, Data count=0)

**Issue**: The QA script couldn't find resolved issues when checking tempo metrics consistency.

**Root Cause**: When history data is not available, the `First Resolved Date` column doesn't exist. The script was only checking for `First Resolved Date` and not falling back to `Resolution Date for Tempo`.

**Fix**: Updated the check to:
- First check if `First Resolved Date` exists and has data
- If not, fall back to `Resolution Date for Tempo`
- Handle the case where neither column exists or has data

**Status**: ✅ Fixed - Now properly handles fallback to Resolution Date for Tempo

## Testing

After these fixes, the QA script should:
1. ✅ Not report status distribution as an error (info only)
2. ✅ Correctly read the Applied count from the report
3. ✅ Properly count resolved issues even without history data

## Next Steps

Run the QA script again to verify all issues are resolved:

```bash
python scripts/qa-applied-issues-report.py \
    -i data/working/issue-analysis/2025/2025-AllYear/2025-all-resolved-issues-enhanced-v3.csv \
    -r data/working/issue-analysis/2025/2025-AllYear/2025-all-resolved-issues-enhanced-v3_analysis.md \
    -p 2025
```

Expected result: No errors, only informational messages about expected behavior (status distribution excluding inferred statuses, etc.)
