# Physics-Informed Harsh-Condition Stability Model

## What Changed

The original `pce_then_stability_same_approach.py` stability models were
empirical machine-learning models. They could use reported stability outcomes,
but they did not normalize measurements taken under different temperatures,
humidities, or illumination intensities.

The model now preserves those empirical baselines and adds a separate,
physics-informed harsh-condition layer. This layer is semi-empirical. It is not
a fully mechanistic chemical degradation model.

## Physical Normalization

For rows with reported stability-test temperature, relative humidity, light
intensity, and degradation evidence, the script calculates:

```text
AF_temperature = exp[(Ea / kB) * (1 / T_ref - 1 / T_test)]
AF_humidity    = 1, when RH <= RH_ref
                 (RH / RH_ref)^n_RH, otherwise
AF_light       = (light / light_ref)^n_light
AF_total       = AF_temperature * AF_humidity * AF_light
```

An observed degradation rate is estimated from end retention and exposure time,
or from T80 when end-retention evidence is unavailable:

```text
k_obs = (-ln(retention_fraction))^(1 / beta) / exposure_hours
k_ref = k_obs / AF_total
T80_ref = (-ln(0.80))^(1 / beta) / k_ref
```

Default reference conditions and assumptions:

```text
T_ref       = 300 K
RH_ref      = 20%
light_ref   = 1 sun
Ea          = 0.60 eV
n_RH        = 1.0
n_light     = 0.70
beta        = 1.0
```

These assumptions are configurable and should be sensitivity-tested before
making scientific claims.

## Model Families

The script now compares three clearly labeled families:

1. `empirical_baseline`
   Preserves the original design-only, predicted-PCE, and measured-initial-
   performance stability models.

2. `physical_condition_features`
   Adds explicit temperature, humidity, and light acceleration factors when
   predicting empirical stability outcomes.

3. `condition_normalized_hybrid`
   Uses material/device/design features to predict degradation rate and T80
   normalized to the reference condition. Raw stability outcomes and harsh-test
   factors are excluded from these hybrid input features to avoid leakage.

## Current Data Coverage

Audit performed on:

```text
E:\LiteratureAgent\artifacts_literature_dataset_update\updated_perovskite_database_with_literature_agent.csv
```

Current coverage:

```text
Total rows:                            43,533
Rows with observed degradation rate:   6,610
Rows with all three harsh conditions:  1,093
Valid condition-normalized targets:       972
```

The 972 condition-normalized rows exceed the default 300-row regression
threshold, so the hybrid family can train on the current integrated database.

## Important Outputs

```text
stability/physical_layer/physical_model_parameters.json
stability/physical_layer/physical_condition_column_mapping.json
stability/physical_layer/physical_condition_coverage.csv
stability/physical_layer/physical_target_exclusion_summary.csv
stability/physical_layer/physical_stability_target_audit.csv
stability/physical_layer/physical_targets_preview.csv
stability/physical_layer/physical_layer_warnings.txt
stability/physical_vs_empirical_model_comparison.csv
```

The physical-layer folder also contains acceleration-factor and predicted-vs-
actual plots.

## Run Commands

Run empirical and physics-informed families:

```powershell
python .\models\pce_then_stability_same_approach.py `
  --csv "E:\LiteratureAgent\artifacts_literature_dataset_update\updated_perovskite_database_with_literature_agent.csv" `
  --out "E:\LiteratureAgent\artifacts_pce_then_stability_lit_updated"
```

Run only the original empirical baseline:

```powershell
python .\models\pce_then_stability_same_approach.py `
  --csv "E:\LiteratureAgent\artifacts_literature_dataset_update\updated_perovskite_database_with_literature_agent.csv" `
  --out "E:\LiteratureAgent\artifacts_pce_then_stability_empirical_only" `
  --disable-physical-stability-layer
```

Example sensitivity run with different assumptions:

```powershell
python .\models\pce_then_stability_same_approach.py `
  --csv "E:\LiteratureAgent\artifacts_literature_dataset_update\updated_perovskite_database_with_literature_agent.csv" `
  --out "E:\LiteratureAgent\artifacts_pce_then_stability_physics_sensitivity" `
  --phys-ea-ev 0.50 `
  --phys-rh-exponent 1.5 `
  --phys-light-exponent 1.0 `
  --phys-beta 1.0
```

## Scientific Interpretation

The empirical models answer: "What stability outcome is associated with this
design in the available literature?"

The condition-aware model answers: "How does the reported outcome vary when the
harsh-test conditions are included explicitly?"

The condition-normalized hybrid answers: "What degradation behavior is
predicted after normalizing reported tests to a common reference condition?"

The physical assumptions should be calibrated or replaced with
mechanism-specific models when enough failure-mode-resolved data becomes
available.
