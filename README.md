# pooled-PPI


A scalable protein-protein interaction screening workflow using AlphaFold 3.

## Background and Original Reference

This project is inspired by the pooled-AlphaFold3 strategy described in:

> Todor, H., Kim, L.M., Jänes, J. et al. **Predicting the protein interaction landscape of a free-living bacterium with pooled-AlphaFold3.** *Molecular Systems Biology* 22, 497–518 (2026). https://doi.org/10.1038/s44320-026-00189-7

The original pooled-PPI method was developed for genome-scale **all-vs-all** PPI screening and was applied to predict the interaction landscape of *Mycoplasma genitalium*.

Original resources:

* Paper: https://link.springer.com/article/10.1038/s44320-026-00189-7
* Original GitHubs: - https://github.com/jurgjn/pooled-ppi/tree/main  - https://github.com/horiatodor/pooled-af3

This repository adapts and extends the pooled-PPI idea for a different use case: **one-vs-all bait-prey screening**. In this setting, the goal is not to observe every possible protein pair. Instead, the bait protein is included in every pool, and each prey protein is observed the desired number of times.

Compared with the original all-vs-all design, this implementation adds a probabilistic, length-weighted pooling strategy optimized for one-vs-all screening.


A scalable protein-protein interaction screening workflow using AlphaFold 3.

pooled-PPI reduces the cost of large-scale PPI prediction by grouping proteins into pools, generating AlphaFold-compatible inputs, extracting pairwise interaction scores from pooled predictions, correcting for pool-size effects, and producing a ranked interaction table.

---

## Overview

The workflow is designed primarily for **one-vs-all screening**, where one bait protein is screened against many prey proteins.

```text
Filtered protein FASTA
        ↓
Pool generation
        ↓
AlphaFold3 JSON generation
        ↓
Input validation
        ↓
AlphaFold prediction
        ↓
Score extraction
        ↓
Size correction
        ↓
Replicate aggregation
        ↓
Final ranked interaction table
```

---

## Main Features

* One-vs-all pooled PPI screening
* Probabilistic length-weighted pooling
* AlphaFold Server input generation
* AlphaFold3 local/HPC input generation
* JSON validation before AF3 submission
* Pairwise score extraction from AF3 outputs
* Size correction
* Replicate aggregation
* Optional HPC/MSA-cache workflow for large-scale screens

---

## Installation

Clone the repository:

```bash
git clone https://github.com/masoomeshafiee/PPI_screening_pipeline
cd pooled-ppi
```

Create the Conda environment:

```bash
conda env create -f environment.yml
conda activate pooled_ppi
```

Verify installation:

```bash
python src/workflow.py --help
```

---

## Basic Usage

The workflow has two main stages:

```yaml
workflow:
  stage: prepare
```

and:

```yaml
workflow:
  stage: process
```

---

# Step 1 — Prepare Input Proteins

Place raw input files (proteom FASTA and the uniprot annotation) in:

```text
data/raw/
```
Update the `config/proteome_filtering_config.yaml` file to filter the proteom of interest with the desired filters (Consult `docs/proteom_filtering.md` for more information).

Run protein filtering:

```bash
python src/seq_filtering/filter_proteins.py
```

This generates:

```text
data/processed/candidate_proteins.fasta
data/processed/candidate_proteins.csv
data/processed/excluded_proteins_with_reasons.csv
data/processed/all_proteins_annotated.csv
```

---

# Step 2 — Configure the Workflow

For detailed information check `Docs/config.md`

Edit:

```text
configs/config.yaml
```

Example:

```yaml
workflow:
  stage: prepare

project:
  name: holC_screen
  output_dir: ./data/output

mode: one_vs_all
approach: probabilistic

input:
  fasta_path: ./data/processed/candidate_proteins.fasta
  target_id: CCNA_01764

pooling:
  max_pool_size: 3000 # max accepted by alphafold is 5000, but after benchmarking realized its better to keep the pool size smaller. 
  n_replicates: 1
  seed: 42
  weighting: length
  shuffle_ties: true

alphafold3:
  dialect: alphafoldserver
  model_seeds: [1]
  version: 1


json_preparation_options:
  overwrite: true

validation:
  json_dir: ./data/output/holC_screen/alphafold3_jsons # if run validation module separately, set this to the directory containing the jsons to validate
  chain_mapping_tsv: ./data/output/holC_screen/pool_chain_mapping.tsv # if run validation module separately, set this to the chain mapping tsv to use for validation
  max_pool_size: 3000

prediction:
  predictions_dir: ./data/output/holC_screen/alphafold3_predictions # set this to the directory containing the AF3 predictions, which should be organized in subdirectories for each pool, and within those, subdirectories for each model seed, e.g. pool_1/model_seed_1/, pool_1/model_seed_2/, etc.

extraction_options:
  use_top_ranked_only: true
  include_self_pairs: false

size_correction:
  score_column: chain_pair_iptm

  method: fit_from_data

  root_to_use: 0.5
  type_of_correction: subtract

  fixed_intercept: 0.04
  fixed_slope: 0.0044

aggregation:
  resolve_replicates: mean


bait_analysis:
  protein_of_interest: Rfa1
  sort_columns:
    - raw_score_resolved
  score_col_for_plotting: raw_score_resolved
  top_n: 50
  protein_1_col: protein_1
  protein_2_col: protein_2

```

---

# Step 3 — Generate Pools and AF3 JSONs

Run:

```bash
python src/workflow.py --config configs/config.yaml
```

This produces:

```text
pools.tsv
pool_summary.tsv
pool_chain_mapping.tsv
af3_json_validation_summary.tsv
alphafold3_jsons/
```

---

# Step 4 — Run AlphaFold

AlphaFold execution is performed outside pooled-PPI.

Supported options:

## AlphaFold Server

Use:

```yaml
alphafold3:
  dialect: alphafoldserver
```

Upload generated JSON files or batch files from:

```text
alphafold3_jsons/
```

Download completed prediction folders into:

```text
alphafold3_predictions/
```

## AlphaFold3 on HPC

Use:

```yaml
alphafold3:
  dialect: alphafold3
  version: 4
```

Run generated JSONs using your local/HPC AlphaFold3 installation.

See:

```text
docs/alphafold3_hpc.md
```

---

# Step 5 — Process AlphaFold Results

After AlphaFold predictions are complete, update the config:

```yaml
workflow:
  stage: process

prediction:
  predictions_dir: /path/to/alphafold3_predictions
```

Run:

```bash
python src/workflow.py --config configs/config.yaml
```

This produces:

```text
pair_scores_raw.tsv
prediction_summary.tsv
pair_scores_size_corrected_observations.tsv
size_correction_model.tsv
pair_scores_size_corrected_aggregated.tsv
```

The final ranked interaction table is:

```text
pair_scores_size_corrected_aggregated.tsv
```

---

# Step 6 — Bait-Specific Analysis

During the `process` stage, the workflow also performs bait-specific analysis using the final aggregated interaction table.

Input:

```text
pair_scores_size_corrected_aggregated.tsv
```

Output:

```text
bait_analysis/
├── filtered_<protein_of_interest>_<sort_column>.tsv
├── ranked_interaction_scores_<protein_of_interest>.svg
└── score_distribution_<score_column>.svg
```

The bait-analysis step filters the final ranked interaction table to keep only interactions involving a selected protein of interest. For one-vs-all screening, this is usually the bait protein defined by:

```yaml
input:
  target_id: CCNA_01764
```

The bait-analysis configuration can be set in `configs/config.yaml`:

```yaml
bait_analysis:
  protein_of_interest: CCNA_01764
  sort_columns:
    - raw_score_resolved
  score_col_for_plotting: raw_score_resolved
  top_n: 50
  protein_1_col: protein_1
  protein_2_col: protein_2
```

This produces a bait-specific ranked table:

```text
bait_analysis/filtered_CCNA_01764_raw_score_resolved.tsv
```

and summary plots for inspecting the strongest predicted interactors and the score distribution.

This step is useful for:

* Identifying top candidate interactors for a bait protein
* Prioritizing proteins for experimental validation
* Inspecting whether a small number of proteins score much higher than the rest
* Generating quick visual summaries of bait-specific results


---

## Important Notes

### AlphaFold is not included

This repository does not include AlphaFold 3, model weights, or AlphaFold databases.

Users must run predictions through:

* AlphaFold Server
* local AlphaFold3
* HPC AlphaFold3

---

### AlphaFold Server vs HPC JSONs

The JSON input formats are different.

Use:

```yaml
dialect: alphafoldserver
```

for AlphaFold Server.

Use:

```yaml
dialect: alphafold3
```

for local/HPC AlphaFold3.

---

### Keep the chain mapping file

Do not delete:

```text
pool_chain_mapping.tsv
```

This file is required to map AlphaFold chain IDs back to protein IDs during score extraction.

---

### Keep full AlphaFold result folders

Do not keep only structure files.

The pipeline needs confidence files such as:

```text
*_summary_confidences.json
```

---

### MSA generation is the main HPC bottleneck

For large-scale HPC runs, the AlphaFold3 data pipeline can be much slower than inference.

For genome-scale screens, consider:

* MSA caching
* SLURM arrays
* reduced array concurrency
* scratch database copies
* resource benchmarking

See:

```text
docs/alphafold3_optimization.md
```

---

## Documentation

| Document                          | Purpose                                     |
| --------------------------------- | ------------------------------------------- |
| `docs/installation.md`            | Installation and environment setup          |
| `docs/workflow.md`                | End-to-end workflow logic                   |
| `docs/config.md`                  | Configuration file reference                |
| `docs/inputs_outputs.md`          | Input/output file reference                 |
| `docs/server/alphafold3_server.md`       | Using AlphaFold Server                      |
| `docs/HPC/alphafold3_hpc.md`          | Running AlphaFold3 on HPC                   |
| `docs/HPC/large_scale_optimization.md` | Large-scale optimization and MSA caching    |
| `docs/developer_guide.md`         | Internal architecture and development notes |
| `docs/proteom_filtering.md`         | Guid about proteom filtering script |

---

## Recommended First Test

Before running a large screen:

1. Use a small FASTA with 5–10 proteins.
2. Run `prepare`.
3. Submit one pool to AlphaFold Server.
4. Download the full result folder.
5. Run `process`.
6. Inspect the final ranked table.

This validates the full workflow before expensive large-scale runs.

---

## Citation

If you use this workflow, please cite:

* AlphaFold 3
* The pooled-PPI reference paper
* This repository
