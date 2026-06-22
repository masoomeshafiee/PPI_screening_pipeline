# Configuration

All workflow behavior is controlled through a single YAML configuration file.

The configuration file defines:

* Project information
* Pooling strategy
* AlphaFold3 JSON generation settings
* Validation settings
* Prediction locations
* Score extraction options
* Size correction parameters
* Replicate aggregation


Important note: beside input_dir and output_dir, you dont need to change the other dir in the config file if you running the modules directly by running the workflow.py.
The module-spesific input/output directories in the config file is only used when running the spesific module standalone. 
---

# Workflow

```yaml
workflow:
  stage: prepare
```

Controls which part of the pipeline is executed.

### Options

#### prepare

Runs:

* Pool generation
* AlphaFold3 JSON generation
* Input validation

Use this stage before running AlphaFold3.

---

#### process

Runs:

* Score extraction
* Size correction
* Replicate aggregation

Use this stage after AlphaFold3 predictions have completed.

---

# Project

```yaml
project:
  name: rfa1_v0_hpc
  output_dir: ./data/output
```

## name

Unique identifier for the analysis.

A project-specific directory will be created inside:

```text
output_dir/project_name/
```

---

## output_dir

Root directory where workflow outputs are stored.

---

# Pooling Strategy

## mode

```yaml
mode: one_vs_all
```

### Supported values

```yaml
one_vs_all
```

Current implementation only supports one-vs-all screening.

The bait protein is included in every pool.

---

## approach

```yaml
approach: probabilistic
```

### Supported values

```yaml
probabilistic
deterministic
```

#### probabilistic

Proteins are sampled using weighted probabilities until the requested number of observations is achieved.

Recommended for large screens.

#### deterministic

Original pooled-PPI style deterministic placement.

Currently requires:

```yaml
n_replicates: 1
```

---

# Input

```yaml
input:
  fasta_path: candidate_proteins.fasta
  target_id: RFA1
```

## fasta_path

Path to the candidate protein FASTA.

---

## target_id

Bait protein identifier.

This protein is included in every pool.

The identifier must exactly match a FASTA record ID.

---

# Pooling Parameters

```yaml
pooling:
  max_pool_size: 3000
  n_replicates: 1
  seed: 42
  max_protein_size: null
  weighting: length
  shuffle_ties: true
```

---

## max_pool_size

Maximum total amino-acid length allowed within a pool. Maximum allowed by alphafold3 is 5000 aa. 

Example:

```yaml
max_pool_size: 3000
```

Smaller values:

* More pools
* Faster AlphaFold jobs

Larger values:

* Fewer pools
* Longer AlphaFold jobs

---

## n_replicates

Number of times each prey protein should be observed.

Example:

```yaml
n_replicates: 3
```

Each prey will appear in approximately three independent pools.

---

## seed

Random seed used for reproducible pool generation.

---

## max_protein_size

Optional upper limit for protein length.

Example:

```yaml
max_protein_size: 2000
```

Proteins longer than this threshold are excluded.

Use:

```yaml
max_protein_size: null
```

to disable filtering.

---

## weighting

Controls protein sampling priority.

### Supported values

```yaml
length
```

#### length

Longer proteins receive higher sampling priority.

This generally reduces the total number of pools required.

---

## shuffle_ties

```yaml
shuffle_ties: true
```

Randomly breaks ties when proteins have identical weights.

---

# AlphaFold3 JSON Generation

```yaml
alphafold3:
  model_seeds: [1]
  dialect: alphafold3
  version: 4
  use_structure_template: true
  count: 1
```

---

## model_seeds

AlphaFold model seeds.

Example:

```yaml
model_seeds: [1]
```

Multiple seeds can be specified:

```yaml
model_seeds: [1,2,3]
```

---

## dialect

Determines the JSON format.

### Supported values

```yaml
alphafoldserver
alphafold3
```

#### alphafoldserver

Google AlphaFold Server format.

#### alphafold3

Local or HPC AlphaFold3 installation format.

---

## version

AlphaFold JSON schema version.

Recommended:

```yaml
version: 1
```

for AlphaFold Server

```yaml
version: 4
```

for local/HPC AlphaFold3

---

## use_structure_template

```yaml
use_structure_template: true
```

If enabled, AlphaFold is allowed to use structural templates.

---

## count

```yaml
count: 1
```

Number of copies of each protein chain in the generated AlphaFold JSON.

Normally left at:

```yaml
count: 1
```

---

# JSON Generation Options

```yaml
json_preparation_options:
  overwrite: true
```

## overwrite

Replace existing JSON files if they already exist.

---

# Validation

```yaml
validation:
  max_pool_size: 3000
```

## max_pool_size

Maximum allowed pool size during validation.

Used as a safety check to ensure generated pools satisfy the desired constraints.

---

# Prediction Inputs

```yaml
prediction:
  predictions_dir: ./alphafold3_predictions
```

Directory containing AlphaFold prediction outputs.

Expected structure:

```text
alphafold3_predictions/
├── pool_00001/
├── pool_00002/
├── pool_00003/
└── ...
```

---

# Score Extraction

```yaml
extraction_options:
  use_top_ranked_only: true
  include_self_pairs: false
```

---

## use_top_ranked_only

If enabled, only the top-ranked AlphaFold prediction is used.

Recommended:

```yaml
true
```

---

## include_self_pairs

Controls whether self-interactions are reported.

Recommended:

```yaml
false
```

---

# Size Correction

```yaml
size_correction:
  score_column: chain_pair_iptm
  method: fit_from_data
  root_to_use: 0.5
  type_of_correction: subtract
  fixed_intercept: 0.04
  fixed_slope: 0.0044
```

---

## score_column

Score used for interaction ranking.

Recommended:

```yaml
chain_pair_iptm
```

---

## method

### Supported values

```yaml
fit_from_data
pooled_ppi_fixed
```

#### fit_from_data

Fits correction coefficients directly from the dataset.

Recommended.

#### pooled_ppi_fixed

Uses coefficients reported in the pooled-PPI publication.

---

## root_to_use

Exponent used when modeling pool-size effects.

Default:

```yaml
0.5
```

Corresponds to square-root scaling.

---

## type_of_correction

### Supported values

```yaml
subtract
```

Current recommended method.

---

## fixed_intercept

Intercept used when:

```yaml
method: pooled_ppi_fixed
```

---

## fixed_slope

Slope used when:

```yaml
method: pooled_ppi_fixed
```

---

# Replicate Aggregation

```yaml
aggregation:
  resolve_replicates: mean
```

Controls how repeated observations of the same interaction are combined.

### Supported values

```yaml
mean
```

The final interaction score is the arithmetic mean across all replicate observations.


--- 

# Bait Analysis

```yaml
bait_analysis:
  protein_of_interest: RFA1
  sort_columns:
    - raw_score_resolved
  score_col_for_plotting: raw_score_resolved
  top_n: 50
  protein_1_col: protein_1
  protein_2_col: protein_2
```

The bait analysis step filters the final size-corrected interaction table to keep only interactions involving one protein of interest.

This step runs during the `process` stage after:

* Score extraction
* Size correction
* Replicate aggregation

It produces a bait-specific ranked interaction table and summary plots.

---

## protein_of_interest

Protein identifier used for bait-specific filtering.

Example:

```yaml
protein_of_interest: RFA1
```

Only interactions where this protein appears in either `protein_1` or `protein_2` are kept.

The identifier must exactly match the protein IDs used in the final aggregated interaction table.

---

## sort_columns

Column or columns used to rank the filtered interactions.

Example:

```yaml
sort_columns:
  - raw_score_resolved
```

The filtered bait-specific table is sorted in descending order using these columns.

---

## score_col_for_plotting

Score column used for bait-analysis plots.

Example:

```yaml
score_col_for_plotting: raw_score_resolved
```

This column is used to generate plots such as:

* Ranked interaction score plot
* Score distribution plot

Usually, this should match the main ranking column used in `sort_columns`.

---

## top_n

Number of top-ranked interactions to show in the ranked score plot.

Example:

```yaml
top_n: 50
```

Smaller values make the plot easier to read.

Common choices:

```yaml
top_n: 20
top_n: 50
top_n: 100
```

---

## protein_1_col

Name of the column containing the first protein in each interaction pair.

Default:

```yaml
protein_1_col: protein_1
```

Usually, this does not need to be changed.

---

## protein_2_col

Name of the column containing the second protein in each interaction pair.

Default:

```yaml
protein_2_col: protein_2
```

Usually, this does not need to be changed.

---

## Outputs

The workflow creates a bait-analysis output directory inside the project directory:

```text
output_dir/project_name/bait_analysis/
```

This directory contains:

```text
filtered_<protein_of_interest>_<sort_column>.tsv
ranked_interaction_scores_<protein_of_interest>.svg
score_distribution_<score_column>.svg
```

The filtered TSV contains only interactions involving the selected protein of interest, sorted by the selected score column.
