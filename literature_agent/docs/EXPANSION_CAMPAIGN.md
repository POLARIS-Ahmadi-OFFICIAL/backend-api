# LiteratureAgent Expansion Campaign

The expansion workflow grows model-ready PCE and stability target support in controlled,
resumable batches. It preserves the existing extraction quality, strict evidence checks,
figure reports, raw outputs, JSON repair, caching, and separate vision pass.

The campaign controller overrides the broad embedded search with a target-rich expansion
query containing device, PCE/J-V, stability, T80/T95, retention, aging-condition, and
encapsulation terms. Paper-type gating still prevents full device extraction on irrelevant
results. It also passes `--disable_google_drive 1`, so expansion batches are strictly
search/download-only even if old Google Drive environment settings remain on the machine.

## Success Criteria

A batch is not successful merely because rows were accepted. It passes QA only when it
adds at least one strict model-ready PCE or stability row. The audit also reports
physical-stability-ready rows with target, temperature, humidity, and illumination data.

## Batch Sequence

Run the 100-paper pilot first:

```powershell
python .\scripts\run_expansion_campaign.py --stage pilot
```

Google Drive credentials are not used by expansion campaign runs.

Review the generated `BATCH_QA_SUMMARY.md`, eligibility CSV, and target-support plots.
Only scale after the pilot passes:

```powershell
python .\scripts\run_expansion_campaign.py --stage scale
```

Continue in resumable 1000-paper batches toward 5000 papers:

```powershell
python .\scripts\run_expansion_campaign.py --stage full
```

For a large campaign, rotate target-rich queries across batches so Crossref does not
repeatedly return the same candidate pool. The campaign manifest records each query.

Run a model check for a batch only when target support changes enough to justify training:

```powershell
python .\scripts\run_expansion_campaign.py --stage scale --run-model-check
```

Preview all commands without running extraction:

```powershell
python .\scripts\run_expansion_campaign.py --stage pilot --dry-run
```

## Batch Outputs

Each batch receives a timestamped folder under `E:\LiteratureAgent\expansion_campaign`.
It contains:

- `batch_manifest.json`
- integration accepted/rejected/audit outputs
- `qa/BATCH_QA_SUMMARY.md`
- `qa/target_support_summary.csv`
- `qa/accepted_rows_with_model_eligibility.csv`
- `qa/target_support_before_after.png`
- `qa/target_support_delta.png`

The shared `E:\LiteratureAgent\lit_outputs` directory remains the resumable cache and
paper registry. Existing outputs are preserved.

For the first campaign batch, target support is compared with the original database.
Later batches are compared with the preceding campaign batch, so the reported target
gain is incremental rather than a misleading cumulative total.

## Knowledge-Graph Plots

The generic relationship-verb count is a pipeline diagnostic, not a scientific result.
Create specific relationship plots from the graph with:

```powershell
python .\scripts\plot_specific_knowledge_relationships.py `
  --graph-dir E:\LiteratureAgent\artifacts_literature_knowledge_graph
```

Use `specific_repeated_scientific_relationships.png` and
`specific_intervention_outcome_relationships.png` in reports.
