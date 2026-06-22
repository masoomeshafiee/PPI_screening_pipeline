# Workflow

## Overview

Pooled-PPI is a scalable protein-protein interaction (PPI) screening workflow built on AlphaFold 3. The pipeline reduces the computational cost of large-scale interaction prediction by grouping proteins into pools, extracting pairwise interaction scores from pooled predictions, and applying correction and aggregation procedures to generate a ranked interaction network.

#### The initial concept is inspired by the pooled-PPI framework described in the following paper:

Large-scale protein interaction screening using pooled AlphaFold predictions (Nature Computational Science, 2026): https://link.springer.com/article/10.1038/s44320-026-00189-7 

The original method was designed for all-vs-all interaction screening. However, the primary use case motivating this project is one-vs-all screening, where a single bait protein is screened against a large set of candidate prey proteins.

To support this use case, the workflow extends the original deterministic pooling strategy with an additional probabilistic pooling algorithm optimized for bait-prey screening.


Probabilistic Pooling Strategy

In the original all-vs-all formulation, the objective is to ensure that every protein pair is observed at least once across all pools.

For one-vs-all screening, this requirement is unnecessarily restrictive. Instead, the objective becomes:

- Ensure that every prey protein is observed the desired number of times.
- Include the bait protein in every pool.
- Minimize the number of pools while maintaining sufficient coverage.

The algorithm starts with an empty set of pools and prioritizes proteins that have not yet reached their target number of observations. Proteins are sampled using a weighted probability distribution, where protein length is used as the weight. This preferentially places longer proteins first, reducing fragmentation and minimizing the total number of pools required.

When multiple proteins have identical lengths, selection is randomized.


---

## Supported AlphaFold Backends

The workflow currently supports:

AlphaFold Server
Local AlphaFold 3 installations
HPC AlphaFold 3 installations 

---

## Workflow Phases

The pipeline is divided into two major phases:

- Preparation
- Processing


## High-Level Workflow

```text

Filtered proteome FASTA
  ↓
Pool generation
  ↓
AlphaFold3 JSON generation
  ↓
JSON validation
  ↓
AlphaFold3 prediction
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

# Phase 1 — Preparation

Depending on the biological question, proteins may be filtered before screening. This reduces computational cost and focuses the analysis on proteins more likely to participate in soluble protein-protein interactions.

The provided filtering script currently supports removal of:

- Ribosomal proteins
- Membrane proteins
- Outer membrane and cell wall synthesis proteins
- Periplasmic proteins

The filtering workflow uses:

Proteome FASTA
+
UniProt annotation table

and generates:

- candidate_proteins.fasta
- candidate_proteins.csv
- excluded_proteins_with_reasons.csv
- all_proteins_annotated.csv

The excluded protein table records the reason(s) each protein was removed, allowing easy quality control and review.

Additional filtering rules can be added by implementing new filtering functions.


Running the filtering step
```
python src/seq_filtering/filter_proteins.py
```
Input files should be placed in:

- data/raw/

Generated outputs are written to:

- data/processed/

---
## Step 1 — Load Protein Sequences

Input:

```text
candidate_proteins.fasta
```

The FASTA file contains all proteins selected for screening.

---

## Step 2 — Generate Pools

Input:

```text
candidate_proteins.fasta
```

Output:

```text
pools.tsv
pool_summary.tsv
```

Proteins are grouped into AlphaFold jobs according to the selected pooling strategy.

Modes:

### One-vs-All

A single bait protein is screened against many prey proteins. ( There are multiple pooling strategies for this step.) 

```text
bait + prey subset #1
bait + prey subset #2
bait + prey subset #3
...
```

### All-vs-All (Not supported by our pipeline) 

All proteins are distributed across pools and pairwise interactions are inferred from pooled predictions, following the strategy described in the original publication.

See config.md for a detailed description of pooling parameters and strategies.

---

## Step 3 — Build AlphaFold3 JSON Inputs

Input:

```text
candidate_proteins.fasta
pools.tsv
```

Output:

```text
alphafold3_jsons/
pool_chain_mapping.tsv
```

For each pool, an AlphaFold3-compatible JSON file is generated.

The chain mapping file records the relationship between:

```text
Pool
Chain ID
Protein ID
Protein Length
```

This mapping is required later when extracting pairwise interaction scores.

JSON files are automatically generated according to the official AlphaFold 3 input specifications. The workflow supports both AlphaFold Server and local/HPC AlphaFold 3 dialects and generates the appropriate format automatically based on the selected configuration.

---

## Step 4 — Validate AlphaFold3 Inputs

Input:

```text
alphafold3_jsons/
pool_chain_mapping.tsv
```

Output:

```text
af3_json_validation_summary.tsv
```

Validation checks include:

* JSON schema validation
* Sequence presence
* Duplicate identifiers
* Chain mapping consistency
* Pool size limits
* AlphaFold3 compatibility

This step is designed to catch common input errors before expensive AlphaFold jobs are launched.

This step catches common errors before expensive AlphaFold jobs are launched.

---

# Phase 2 — AlphaFold3 Prediction

AlphaFold3 prediction is executed outside the pooled-PPI workflow.

Supported execution environments:

## AlphaFold Server

Advantages:

* No installation required
* Simple workflow, minimal user experties and cognitive load
* Suitable for small and medium projects

Limitations:

* Manual upload/download 
* Queue limitations ( 30 qouta per day, so 30 jobs per day for each google acount)
* Less automation

## AlphaFold3 on HPC

Advantages:

* Fully automated
* Suitable for genome-scale screens but in theory! (read the `docs/HPC/large_scale_optimization.md` for more)
* Supports MSA caching workflows

Limitations:

* Requires HPC resources (for the large-scale screening, the queue time might be high, SLURM array limit is also 1000 for the lab account)
* Requires AlphaFold3 installation + request to access the weights of the model directly from google.
* requries the msa chacing for the large-scale screeing
* requuires familarity with HPC, SLURM, resource allocation, linux, bash

So for our lab resources and experites now I recommend the server.

Once you are done with the af3 inference, download and put the foldrs for each job in side this:

Output:

```text
alphafold3_predictions/
```

Each pool produces AlphaFold3 prediction outputs and confidence summaries.

---

# Phase 3 — Score Extraction

Input:

```text
alphafold3_predictions/
pool_chain_mapping.tsv
```

Output:

```text
pair_scores_raw.tsv
prediction_summary.tsv
```

Pairwise interaction scores are extracted from AlphaFold3 outputs.

Metrics may include:

* chain_pair_iptm
* interface confidence metrics
* ranking scores

Each observation represents a potential interaction observed within a specific pool.

---

# Phase 4 — Size Correction

Input:

```text
pair_scores_raw.tsv
```

Output:

```text
pair_scores_size_corrected_observations.tsv
size_correction_model.tsv
```

Pool size influences AlphaFold interaction scores.

To reduce this bias, pooled-PPI applies a size-correction model.

Supported methods:

* pooled_ppi_fixed
* fit_from_data

The correction model estimates the expected score inflation caused by increasing pool size and adjusts interaction scores accordingly.

---

# Phase 5 — Replicate Aggregation

Input:

```text
pair_scores_size_corrected_observations.tsv
```

Output:

```text
pair_scores_size_corrected_aggregated.tsv
```

The same interaction may be observed multiple times across independent pools.

Replicate observations are combined using the selected aggregation strategy.

Supported methods:

* mean


This step produces a single score per interaction.

---

# Final Output

The final output is a ranked interaction table:

```text
pair_scores_size_corrected_aggregated.tsv
```

Each row represents a predicted protein-protein interaction with:

* Protein A
* Protein B
* Corrected interaction score
* Number of observations
* Aggregated confidence metrics

This table can be used for:

* Interaction ranking
* Network construction
* Candidate prioritization
* Experimental validation

```
```


---

# Phase 6 — Bait Analysis

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

After replicate aggregation, the workflow perform bait-specific analysis.

This step filters the final aggregated interaction table to keep only interactions involving a selected protein of interest. The protein of interest may appear in either `protein_1` or `protein_2`.

For one-vs-all screening, this is usually the bait protein defined in the configuration file as:

```yaml
input:
  target_id: RFA1
```

The bait-analysis step produces a ranked table of candidate interactors for the selected protein and generates summary plots to support downstream interpretation.

The filtered output table is sorted using the selected score column, for example:

```yaml
sort_columns:
  - raw_score_resolved
```

This step is useful for:

* Identifying the top predicted interaction partners of a bait protein
* Prioritizing candidates for experimental validation
* Visualizing score distributions
* Comparing the strongest candidates against the full bait-specific score profile

The main bait-specific output is:

```text
bait_analysis/filtered_<protein_of_interest>_<sort_column>.tsv
```

For example:

```text
bait_analysis/filtered_RFA1_raw_score_resolved.tsv
```

This file can be used directly for candidate prioritization and downstream biological interpretation.
