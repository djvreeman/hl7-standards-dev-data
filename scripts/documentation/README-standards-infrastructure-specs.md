# SOP: Specifications on HL7 Build and Jira Feedback Infrastructure

Run from the `hl7-standards-dev-data` repo root. This produces the SISC rate-model cells **N**, **T**, and **N − T**. Analyzer and reports live under `scripts/standards-infrastructure-usage/` and `data/working/standards-infrastructure-usage/` (not the ballot-participation pipeline).

Latest scripts: [github.com/djvreeman/hl7-standards-dev-data](https://github.com/djvreeman/hl7-standards-dev-data)

## Operating model

- **T** is unique Jira Specification keys with **at least one issue created** in the lookback. Not a closed BALDEF.
- **N** is CI-build specs in the lookback (International + partners + community) plus issue-only specs that are not on the FHIR IG CI builder.
- **N − T** is build-and-publication only.
- Keep the Jira query **inline** in the command (do not hide it behind a saved filter ID). That makes the universe obvious when you rerun.
- Limit the Jira pull with **`created >= -400d`**. That covers a 365-day lookback with timezone / as-of buffer and cuts the extract from 50k+ issues to ~7–8k. The analyzer still slices **Created Date** to the 365-day window.
- Include affiliates (AU, EU, and every other work group). Do **not** reuse filter 24407: that filter is date-capped and excludes AU/EU; it belongs to the T1 issue-process reports.

Inline JQL (this is the query; keep it in the command):

```
project in (FHIR, CDA, V2, OTHER)
AND Specification is not EMPTY
AND created >= -400d
ORDER BY created DESC
```

Required issue fields: `key`, `fields.created`, `fields.customfield_11302` (Specification). Optional but useful: spec display name, issue type, status.

## How to execute

**1. Refresh specification-feedback issues** (Jira token). Create the output folder first. Do not use `--orgs` on the builds step in #2.

```bash
mkdir -p data/working/issue-analysis/2026/lookback
python3 scripts/parse-jira-filter-export-csv-md.py \
  -f '{"jql": "project in (FHIR, CDA, V2, OTHER) AND Specification is not EMPTY AND created >= -400d ORDER BY created DESC"}' \
  -d 'key,fields.created,fields.customfield_11302,fields.spec_display_name,fields.issuetype.name,fields.status.name' \
  -o data/working/issue-analysis/2026/lookback/YYYYMMDD-all-spec-feedback-issues-400d \
  -e csv --cache --cache-dir data/working/cache
```

Sanity on the CSV: newest **Created Date** should be around today, and you should see `FHIR-au-*` / `FHIR-eu-*` keys. If the newest created date is months old, you used the T1 filter.

**2. Refresh CI-build recent activity** (365 days, every GitHub org, not only `HL7`). Use the **`*-recent-builds.csv`** file, not the unique `*-build-repos.csv` list.

```bash
python3 scripts/parse-builds-web.py --recent --days 365
```

**3. Run the analyzer** (lookback and as-of date must match the inputs):

```bash
python3 scripts/standards-infrastructure-usage/standards-infrastructure-specs-analyze.py \
  --issues-csv data/working/issue-analysis/2026/lookback/YYYYMMDD-all-spec-feedback-issues-400d.csv \
  --recent-builds-csv data/working/builds/<timestamp>-recent-builds.csv \
  -o data/working/standards-infrastructure-usage/reports/YYYY-MM-DD-standards-infrastructure-specs.md \
  --lookback-days 365 \
  --data-gathering-date YYYY-MM-DD \
  --csv data/working/standards-infrastructure-usage/reports/YYYY-MM-DD-standards-infrastructure-specs.csv
```

If the four identity checks on the Full universe row fail, the script exits non-zero. If the issues extract ends more than a week before the as-of date, it warns that T will undercount.

**4. Copy the cells** from **SISC Rate Calculation cells** (immediately after the Summary table): **N**, **T**, and **N − T**. Those are the Full universe row translated (`N = U`, `T = B` = had a Jira issue created, `N − T = Build only`). Do not take T from the HL7 International row.

## Worked example (21 Aug 2026)

Pull: inline JQL with `created >= -400d` → 7,906 issue rows; 7,480 created in the 365-day lookback on 139 Specification keys. Builds: `20260821-060233-recent-builds.csv`.

| SISC cell | Value |
| --- | --- |
| N | 521 |
| T | 138 |
| N − T | 383 |

International: 122 / 169 (72.2%) had an issue created. Partners: 16 / 85 (18.8%). Community: 0.

## Do not

- Do not use filter 24407 or any query with `createdDate <=` a calendar ceiling.
- Do not exclude AU/EU work groups or Specification keys.
- Do not use the unique org/repo builds CSV as `--recent-builds-csv`.
- Do not take T from the International row or from “HL7/ repos that built.”
- Do not drop issue-only specs (V2, older CDA, FHIR Core, …) from N or T.
- Do not print salaries or rates in this report.
