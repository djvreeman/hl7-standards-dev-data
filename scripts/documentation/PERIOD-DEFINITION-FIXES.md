# Period Definition Fixes

## Issue

Sub-period totals (T1 + T2 + T3) didn't match the overall year total. The difference was 67 issues.

## Root Cause

Period end dates were set to `00:00:00` (start of day) instead of `23:59:59.999999` (end of day). This caused boundary issues where:

1. Issues created later in the day on period boundaries (Apr 30, Aug 31, Dec 31) might be counted differently
2. The `<=` comparison with `00:00:00` end dates only includes timestamps at exactly `00:00:00`, not the entire day

## Fix

Updated `parse_time_period()` function in `applied-issues-analyze.py` to use end-of-day timestamps:

### Before:
```python
end_date = pd.Timestamp(year=year, month=4, day=30, tz='UTC')  # 00:00:00
```

### After:
```python
end_date = pd.Timestamp(year=year, month=4, day=30, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')  # 23:59:59.999999
```

## Period Definitions Updated

- **T1**: Jan 1 00:00:00 to Apr 30 23:59:59.999999
- **T2**: May 1 00:00:00 to Aug 31 23:59:59.999999  
- **T3**: Sep 1 00:00:00 to Dec 31 23:59:59.999999
- **Full Year**: Jan 1 00:00:00 to Dec 31 23:59:59.999999

## Applied Count Parsing Fix

Also fixed the QA script's regex pattern to properly parse the "Applied" count from the "Issues by Category" table. The pattern now:

1. First finds the section header
2. Searches within that section for the data row
3. Has a fallback flexible pattern that handles whitespace variations
4. Provides better error messages if parsing fails

## Testing

After these fixes:
- Sub-period totals should match the overall year total exactly
- QA script should correctly parse Applied counts from the report
- All date comparisons will be more precise and consistent

## Impact

- **Breaking Change**: Yes - existing reports generated with old period definitions may show different counts
- **Recommendation**: Regenerate reports with the updated period definitions for accurate totals
