# Prepared Chi/TWOSEX-style matrices

Some workbooks contain a manually prepared individual matrix rather than raw dates or canonical records. A common shape has repeated treatment blocks, columns such as `number`, `sex`, stage durations, `adult`, and then a run of daily fecundity cells beginning under a label such as `egg`.

Run the mechanical audit before attempting to normalize this layout:

```bash
python3 scripts/audit_chi_matrix.py INPUT_FILE \
  --sheet SHEET_NAME \
  --output-dir OUTPUT_DIR/chi_audit
```

The audit deliberately does not infer the following meanings:

- whether `N` means preadult death, unknown sex, or another state;
- whether a negative stage duration marks death and whether its absolute value is the time spent in that stage;
- the identity of any unnamed duration column;
- whether the first fecundity cell is adult interval 0 or 1;
- whether fecundity counts eggs, viable eggs, emerged offspring, daughters, or another outcome;
- whether blanks after the last fecundity value are post-death structural blanks, observed zeros, or missing observations;
- why records were selected from upstream raw sheets and whether exclusions were prespecified.

Treat internal blank intervals, fecundity extending beyond adult longevity, and a fecundity horizon ending more than one interval before adult longevity as calculation-blocking alignment problems. A one-interval difference may reflect a death-day convention but still needs study-specific confirmation.

Do not interpret a prepared matrix as raw evidence. When the workbook also contains upstream raw sheets, preserve a record-level link or reconciliation table from each prepared row back to its source individual. Counts that differ between raw and prepared sheets require an explicit inclusion/exclusion ledger.

After resolving every error and confirming the encodings, convert records to the canonical individual and observation schema. Keep the original stage-duration codes in provenance. Calculate only after the offspring estimand, time origin, death convention, unlisted-zero meaning, and resampling unit are confirmed.
