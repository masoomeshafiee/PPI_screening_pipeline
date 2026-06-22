# Filtering Module Notes (Users and Developers)

## Purpose

The filtering module prepares a clean candidate protein set before the pooled-PPI workflow.

It takes a UniProt-style annotation table and a matching proteome FASTA file, applies configurable exclusion filters, and produces:

```text
all_proteins_annotated.csv
candidate_proteins.csv
excluded_proteins_with_reasons.csv
candidate_proteins.fasta
```

The main goals are to:

- remove proteins that are unlikely to be suitable for soluble pooled-PPI screening
- preserve traceability of every filtering decision
- keep the filtering behavior configurable without changing Python code
- export a FASTA file whose record IDs are compatible with downstream pooling and AlphaFold input generation

---

## Recommended Command

Run the filtering module using a YAML configuration file:

```bash
python3 src/seq_filtering/filter_proteins.py \
  --config configs/proteome_filtering_config.yaml
```

The user should normally edit only the config file, not the Python script.


Example of query for getting the UniProt annotation file with the required columns:
``` text
curl -L "https://rest.uniprot.org/uniprotkb/stream?query=proteome:UP000001364&format=tsv&fields=accession,id,gene_names,protein_name,organism_name,length,cc_subcellular_location,ft_transmem,go,go_c,go_p,go_f,keyword,sequence" \
 -o data/raw/caulobacter_uniprot_annotations.tsv
---

# Configuration File

The filtering module is controlled by a YAML file, for example:

```text
configs/proteome_filtering_config.yaml
```

A typical config has the following sections:

```yaml
input:
  annotation_file: data/raw/caulobacter_uniprot_annotations.tsv
  fasta_file: data/raw/caulobacter_proteome.fasta

output:
  output_dir: data/processed
  all_output: all_proteins_annotated.csv
  candidate_csv: candidate_proteins.csv
  excluded_csv: excluded_proteins_with_reasons.csv
  candidate_fasta: candidate_proteins.fasta

columns:
  accession: Entry
  gene_names: Gene Names

text_columns:
  - Entry
  - Entry Name
  - Gene Names
  - Protein names
  - Organism
  - Subcellular location [CC]
  - Transmembrane
  - Gene Ontology (GO)
  - Gene Ontology (cellular component)
  - Gene Ontology (biological process)
  - Gene Ontology (molecular function)
  - Keywords

filters:
  ribosomal:
    reason: ribosomal
    gene_prefixes:
      - rps
      - rpl
      - rpm
    terms:
      - ribosomal
      - ribosome
      - 30s ribosomal protein
      - 50s ribosomal protein
      - small ribosomal subunit
      - large ribosomal subunit

  membrane_bound:
    reason: membrane_bound
    require_non_empty_column:
      - Transmembrane
    terms:
      - membrane
      - transmembrane
      - integral membrane
      - cell membrane
      - cytoplasmic membrane
      - inner membrane

  outer_membrane_or_cell_wall:
    reason: outer_membrane_or_cell_wall_synthesis
    terms:
      - outer membrane
      - cell wall
      - cell envelope
      - peptidoglycan
      - murein
      - lipopolysaccharide
      - lps biosynthesis
      - udp-n-acetylmuramate
      - muramoyl
      - penicillin-binding protein
      - glycosyltransferase involved in cell wall

  periplasmic:
    reason: periplasmic
    terms:
      - periplasm
      - periplasmic
      - periplasmic space

fasta:
  parser_format: fasta
  rename_header_to_gene_name: true
  require_gene_name: true
```

---

## `input` Section

The `input` section defines the two required input files.

```yaml
input:
  annotation_file: data/raw/caulobacter_uniprot_annotations.tsv
  fasta_file: data/raw/caulobacter_proteome.fasta
```

### `annotation_file`

Path to the UniProt annotation table.

Expected format:

```text
TSV file
```

The annotation file must contain the accession column specified under:

```yaml
columns:
  accession: Entry
```

For UniProt downloads, this is usually:

```text
Entry
```

### `fasta_file`

Path to the proteome FASTA file.

The FASTA records are matched back to the annotation table using UniProt accessions extracted from the FASTA header.

UniProt-style FASTA headers usually look like:

```text
>sp|A0A0H3C8X0|CERS_CAUVN Bacterial ceramide synthase OS=Caulobacter vibrioides ... GN=bcerS ...
```

From this header, the script extracts:

```text
UniProt accession: A0A0H3C8X0
Gene/locus ID:     bcerS
```

---

## `output` Section

The `output` section defines where results are written.

```yaml
output:
  output_dir: data/processed
  all_output: all_proteins_annotated.csv
  candidate_csv: candidate_proteins.csv
  excluded_csv: excluded_proteins_with_reasons.csv
  candidate_fasta: candidate_proteins.fasta
```

The final output paths are built by combining `output_dir` with each filename.

Example:

```text
data/processed/candidate_proteins.csv
```

---

## `columns` Section

The `columns` section tells the script which annotation-table columns contain important identifiers.

```yaml
columns:
  accession: Entry
  gene_names: Gene Names
```

### `accession`

The column used to match annotation rows to FASTA records.

For UniProt annotation tables, this is usually:

```text
Entry
```

### `gene_names`

The column used for gene-name or locus-prefix filtering.

For UniProt annotation tables, this is usually:

```text
Gene Names
```

The filtering module splits this field by whitespace.

Example:

```text
rpsA 30S ribosomal protein S1
```

A configured prefix such as:

```yaml
gene_prefixes:
  - rps
```

will match the gene name:

```text
rpsA
```

---

## `text_columns` Section

The `text_columns` section defines which annotation fields are combined into one searchable text string.

```yaml
text_columns:
  - Entry
  - Entry Name
  - Gene Names
  - Protein names
  - Organism
  - Subcellular location [CC]
  - Transmembrane
  - Gene Ontology (GO)
  - Gene Ontology (cellular component)
  - Gene Ontology (biological process)
  - Gene Ontology (molecular function)
  - Keywords
```

For every protein row, the script:

1. reads these columns if they exist
2. converts missing values to empty strings
3. lowercases the text
4. joins everything into one annotation string

Most term-based filters search this combined annotation text.

Missing optional columns do not stop the script. They are skipped during text construction.

---

# Dynamic Filtering System

The filtering module uses a dynamic config-driven filtering system.

Any filter added under:

```yaml
filters:
```

is automatically applied by the Python script.

This means users no longer need to implement new Python functions such as:

```python
is_ribosomal()
is_membrane_bound()
is_periplasmic()
```

Instead, the script loops over all configured filters and applies the same generic matching logic.

---

## Filter Structure

Each filter can contain the following optional keys:

```yaml
filters:
  filter_name:
    reason: reason_written_to_output
    gene_prefixes:
      - prefix1
      - prefix2
    terms:
      - annotation term 1
      - annotation term 2
    require_non_empty_column:
      - Column Name
```

A protein matches a filter if at least one of the configured rules matches.

That means the logic is:

```text
term match
OR gene-prefix match
OR required-column-is-non-empty match
```

If a protein matches a filter, the filter's `reason` is added to the `exclusion_reason` column.

---

## `reason`

The `reason` field defines the machine-readable label written to the output files.

Example:

```yaml
ribosomal:
  reason: ribosomal
```

If this filter matches, the output will contain:

```text
ribosomal
```

Reason strings should be:

- lowercase
- short
- stable across versions
- machine-readable
- easy to group/count

Good examples:

```text
ribosomal
membrane_bound
periplasmic
outer_membrane_or_cell_wall_synthesis
```

Avoid long sentence-style reasons such as:

```text
This protein appears to be membrane associated
```

---

## `terms`

The `terms` field defines annotation keywords to search for in the combined annotation text.

Example:

```yaml
periplasmic:
  reason: periplasmic
  terms:
    - periplasm
    - periplasmic
    - periplasmic space
```

The search is case-insensitive because all annotation text is lowercased before filtering.

For example, this term:

```text
periplasm
```

can match annotation text such as:

```text
Periplasmic protein
```

because both are normalized to lowercase.

---

## `gene_prefixes`

The `gene_prefixes` field defines gene-name prefixes.

Example:

```yaml
ribosomal:
  reason: ribosomal
  gene_prefixes:
    - rps
    - rpl
    - rpm
```

This will match gene names such as:

```text
rpsA
rplB
rpmC
```

This is useful when proteins can be identified more reliably from gene naming conventions than from annotation text alone.

---

## `require_non_empty_column`

The `require_non_empty_column` field excludes a protein if any listed annotation column exists and has a non-empty value.

Example:

```yaml
membrane_bound:
  reason: membrane_bound
  require_non_empty_column:
    - Transmembrane
```

This means:

```text
If the UniProt Transmembrane column has any content, exclude the protein as membrane_bound.
```

This is useful for columns where the presence of a value is already meaningful.

---

# Current Exclusion Filters

The current recommended filters are:

## Ribosomal Proteins

```yaml
ribosomal:
  reason: ribosomal
  gene_prefixes:
    - rps
    - rpl
    - rpm
  terms:
    - ribosomal
    - ribosome
    - 30s ribosomal protein
    - 50s ribosomal protein
    - small ribosomal subunit
    - large ribosomal subunit
```

This excludes proteins based on:

- ribosomal gene prefixes
- ribosome-related annotation terms

---

## Membrane-Bound Proteins

```yaml
membrane_bound:
  reason: membrane_bound
  require_non_empty_column:
    - Transmembrane
  terms:
    - membrane
    - transmembrane
    - integral membrane
    - cell membrane
    - cytoplasmic membrane
    - inner membrane
```

This excludes proteins if:

- the `Transmembrane` annotation column is non-empty
- or membrane-related terms are found in the combined annotation text

### Important Note

The term:

```text
membrane
```

is broad and may exclude proteins that are only loosely membrane-associated.

For a stricter filter, users may remove the broad term:

```yaml
- membrane
```

and rely on more specific terms such as:

```yaml
- transmembrane
- integral membrane
- inner membrane
```

---

## Outer Membrane or Cell Wall Synthesis Proteins

```yaml
outer_membrane_or_cell_wall:
  reason: outer_membrane_or_cell_wall_synthesis
  terms:
    - outer membrane
    - cell wall
    - cell envelope
    - peptidoglycan
    - murein
    - lipopolysaccharide
    - lps biosynthesis
    - udp-n-acetylmuramate
    - muramoyl
    - penicillin-binding protein
    - glycosyltransferase involved in cell wall
```

This excludes proteins associated with outer membrane localization, envelope biology, and cell wall synthesis.

---

## Periplasmic Proteins

```yaml
periplasmic:
  reason: periplasmic
  terms:
    - periplasm
    - periplasmic
    - periplasmic space
```

This excludes proteins annotated as periplasmic.

---

# Adding a New Filter

To add a new exclusion filter, users only need to edit the config file.

No Python code changes are required.

For example, to exclude flagellar proteins:

```yaml
filters:
  flagellar:
    reason: flagellar
    gene_prefixes:
      - flg
      - fli
      - flh
    terms:
      - flagellar
      - flagellum
      - motility
```

To exclude secretion-system proteins:

```yaml
filters:
  secretion_system:
    reason: secretion_system
    terms:
      - secretion system
      - type ii secretion
      - type iii secretion
      - type iv secretion
      - type vi secretion
```

To exclude proteins with a non-empty signal-peptide column, if such a column exists:

```yaml
filters:
  signal_peptide:
    reason: signal_peptide
    require_non_empty_column:
      - Signal peptide
    terms:
      - signal peptide
      - secreted
```

---

## Important Warning About Filter Meaning

Every filter under:

```yaml
filters:
```

is an exclusion filter.

That means if a user adds:

```yaml
filters:
  cytosol:
    reason: cytosol
    terms:
      - cytosol
      - cytosolic
```

then cytosolic proteins will be excluded.

If future users need both inclusion and exclusion logic, the config should be redesigned as:

```yaml
include_filters:
  cytosol:
    terms:
      - cytosol
      - cytosolic

exclude_filters:
  ribosomal:
    terms:
      - ribosomal
      - ribosome
```

The current implementation treats all filters as exclusion filters.

---

# Filtering Logic

The filtering module creates an `exclusion_reason` column.

If no exclusion rule is triggered:

```text
filter_status = keep
```

If one or more exclusion rules are triggered:

```text
filter_status = exclude
```

Multiple exclusion reasons are stored as semicolon-separated values.

Example:

```text
membrane_bound;periplasmic
```

The dynamic logic is equivalent to:

```python
for filter_name, filter_config in config["filters"].items():
    if matches_filter(row, text, filter_config, config):
        reasons.append(filter_config.get("reason", filter_name))
```

This design allows users to add, remove, or modify filters in the YAML file without modifying the script.

---

# Text Normalization

All annotation text is normalized using:

```python
normalize_text(value)
```

This function:

- converts missing values to an empty string
- converts all text to lowercase

This makes filtering rules case-insensitive and robust to missing values.

---

# Combined Annotation Text

The function:

```python
combined_annotation_text(row, text_columns)
```

combines all configured annotation fields into one searchable lowercase string.

Most filtering rules operate on this combined text.

This design makes the filter system flexible, because any new filter can use the same combined text rather than requiring custom column-specific logic.

---

# FASTA Export Logic

Candidate proteins are selected using UniProt accessions from the annotation table.

The accession column is configured here:

```yaml
columns:
  accession: Entry
```

The script builds the candidate accession set:

```python
candidate_ids = set(kept[accession_col].astype(str))
```

Each FASTA record is matched by extracting the UniProt accession from the FASTA record ID:

```python
extract_uniprot_accession_from_fasta_id(record.id)
```

For retained proteins, the FASTA header can be rewritten using the gene/locus ID extracted from `GN=`.

Example input FASTA header:

```text
>sp|A0A0H3C8X0|CERS_CAUVN Bacterial ceramide synthase OS=Caulobacter vibrioides ... GN=bcerS ...
```

Example output FASTA header:

```text
>bcerS
```

This behavior is controlled by:

```yaml
fasta:
  rename_header_to_gene_name: true
  require_gene_name: true
```

---

## FASTA Parser Format

The FASTA parser format is configurable:

```yaml
fasta:
  parser_format: fasta
```

Supported Biopython parser formats include:

```text
fasta
fasta-blast
fasta-pearson
```

Recommended default:

```yaml
fasta:
  parser_format: fasta
```

If the FASTA file contains comment lines before the first sequence, use:

```yaml
fasta:
  parser_format: fasta-blast
```

If the FASTA file contains blank or non-standard lines before the first sequence, either clean the FASTA file or use:

```yaml
fasta:
  parser_format: fasta-pearson
```

In practice, the cleanest approach is to remove leading blank/comment lines from the FASTA file before running the pipeline.

---

## FASTA Header Renaming

The output FASTA can be configured with:

```yaml
fasta:
  rename_header_to_gene_name: true
```

When this is true, retained FASTA records are rewritten from UniProt-style headers to gene/locus IDs.

Example:

```text
>sp|A0A0H3C8X0|CERS_CAUVN ... GN=bcerS ...
```

becomes:

```text
>bcerS
```

This is important because the rest of the pooled-PPI workflow uses these IDs consistently:

```text
candidate_proteins.fasta header = gene/locus ID
pooling ID = gene/locus ID
MSA JSON name = gene/locus ID
MSA cache file = gene/locus ID.unpaired.a3m
pooled AF3 JSON protein_id = gene/locus ID
```

Do not disable this behavior unless all downstream modules are designed to use UniProt accessions instead.

---

## Missing `GN=` Behavior

The config option:

```yaml
fasta:
  require_gene_name: true
```

means the script will raise an error if a retained FASTA record does not contain a `GN=` field.

This is intentional.

Without a gene/locus identifier, the downstream workflow may produce inconsistent protein IDs.

If supporting organisms or FASTA files without `GN=` fields, developers should implement a fallback identifier strategy explicitly.

A possible fallback strategy is:

```yaml
fasta:
  rename_header_to_gene_name: true
  require_gene_name: false
```

In this case, the script may fall back to the UniProt accession if no `GN=` is found, depending on the implementation.

Do not silently fall back to UniProt accessions unless the entire downstream workflow is designed to accept UniProt IDs.

---

# Identifier Design

A critical design decision is that the final `candidate_proteins.fasta` is usually rewritten to use gene/locus IDs as FASTA record IDs.

Example output:

```fasta
>bcerS
MPFDSTNADLSVIPVKTPAELKRFIALPARLNAKDPNWITPLFMERTDALTPKTNPFFDH...
```

This makes downstream files easier to interpret and keeps protein IDs stable throughout the pooled-PPI workflow.

---

# Duplicate Protein Sequences and Locus IDs

## Background

In some genomes, multiple locus IDs may encode identical amino-acid sequences.

For example:

```text
CCNA_00001 → Protein Sequence A
CCNA_00002 → Protein Sequence A
```

Although the locus IDs differ, the translated protein sequence is identical.

---

## UniProt Annotation Behavior

When UniProt collapses identical proteins into a single protein entry, only one locus identifier may be retained in the annotation table.

Example:

```text
Genome:
    CCNA_00001
    CCNA_00002

Both encode identical proteins.

UniProt annotation:
    Entry → A0A1234567
    Gene Names → CCNA_00001
```

In this situation:

```text
CCNA_00002
```

may not appear anywhere in the downloaded UniProt annotation file.

---

## Current Filtering Behavior

The filtering workflow is annotation-driven.

Candidate proteins are selected using the configured accession column:

```python
candidate_ids = set(kept[accession_col].astype(str))
```

and then matched back to FASTA records using UniProt accessions extracted from FASTA headers.

As a consequence:

- only proteins represented in the annotation table can be retained
- if UniProt collapses multiple locus IDs into a single protein entry, only the representative locus ID will appear in the final outputs

---

## Effect on Output Files

The following files will contain only the representative locus:

```text
candidate_proteins.csv
candidate_proteins.fasta
```

Example:

```text
Genome FASTA:
    CCNA_00001
    CCNA_00002

UniProt annotation:
    CCNA_00001

Output:
    candidate_proteins.fasta
        >CCNA_00001
```

while:

```text
CCNA_00002
```

will not appear.

---

## Biological Interpretation

This behavior is generally acceptable for pooled-PPI because:

1. the encoded protein sequence is identical
2. AlphaFold operates on protein sequence rather than locus identity
3. including both loci would produce duplicate predictions
4. removing duplicates reduces computational cost without losing structural information

In practice, the pooled-PPI workflow screens proteins rather than genomic loci.

---

## Important Caveat

The current workflow does not explicitly detect or report collapsed locus IDs.

If locus-level tracking is important for a project, developers should implement an additional reconciliation step between:

```text
proteome FASTA
```

and:

```text
UniProt annotation table
```

to identify:

- duplicated protein sequences
- collapsed locus identifiers
- one-to-many mapping relationships

before filtering is performed.

For most protein interaction screening applications, the current behavior is acceptable and avoids redundant AlphaFold predictions.

---

# Output Files

## `all_proteins_annotated.csv`

Contains the full annotation table plus:

```text
exclusion_reason
filter_status
```

Useful for auditing and QC.

---

## `candidate_proteins.csv`

Subset of proteins with:

```text
filter_status = keep
```

These are the proteins retained after filtering.

---

## `excluded_proteins_with_reasons.csv`

Subset of proteins with:

```text
filter_status = exclude
```

This is the most important QC file for reviewing filtering decisions.

It allows users to inspect exactly why each protein was excluded.

---

## `candidate_proteins.fasta`

FASTA file containing retained proteins.

Headers are usually rewritten to gene/locus IDs.

Example:

```fasta
>bcerS
MPFDSTNADLSVIPVKTPAELKRFIALPARLNAKDPNWITPLFMERTDALTPKTNPFFDH...
```

This file is the primary input for the pooled-PPI workflow.

---

# Quality Control Recommendations

After running the filtering module, check that output files were created:

```bash
ls -lh data/processed
```

Check the number of retained and excluded proteins:

```bash
wc -l data/processed/candidate_proteins.csv
wc -l data/processed/excluded_proteins_with_reasons.csv
```

Check FASTA headers:

```bash
grep ">" data/processed/candidate_proteins.fasta | head
```

Expected format if FASTA renaming is enabled:

```text
>bcerS
>cgtA
>pleD
```

Not:

```text
>sp|A0A0H3C8X0|CERS_CAUVN
```

Inspect exclusion reasons in Python:

```python
import pandas as pd

excluded = pd.read_csv("data/processed/excluded_proteins_with_reasons.csv")

print(excluded["exclusion_reason"].value_counts())
```

For semicolon-separated multiple reasons, use:

```python
(
    excluded["exclusion_reason"]
    .str.split(";")
    .explode()
    .value_counts()
)
```

---

# Common Issues

## FASTA parser error: comments before first sequence

Error example:

```text
ValueError: This FASTA file contains comments at the beginning of the file
```

Possible fixes:

1. clean the FASTA file so the first non-empty line starts with `>`
2. use `fasta-blast` if the file contains comment lines beginning with `#`, `!`, or `;`
3. use `fasta-pearson` for more permissive parsing

Config example:

```yaml
fasta:
  parser_format: fasta-pearson
```

---

## FASTA parser error: blank line before first sequence

Error example:

```text
ValueError: Expected FASTA record starting with '>' character.
Got: ''
```

This usually means there is a blank line before the first FASTA record.

Recommended fix:

```bash
perl -i -0pe 's/^\s+//' data/raw/caulobacter_proteome.fasta
```

Then use:

```yaml
fasta:
  parser_format: fasta
```

---

## Missing `GN=` in retained FASTA record

Error example:

```text
ValueError: Could not find GN= in FASTA header
```

This means the script tried to rename the FASTA header to a gene/locus ID, but no `GN=` field was found.

Possible fixes:

1. use a FASTA file with UniProt-style `GN=` fields
2. set `require_gene_name: false` only if fallback behavior is implemented and acceptable
3. disable renaming only if downstream modules can use the original FASTA IDs

---

# Known Limitations

The current implementation is still UniProt-oriented because it assumes:

- annotation rows can be matched to FASTA records by UniProt accession
- FASTA accessions can be extracted from headers such as `sp|ACCESSION|NAME` or `tr|ACCESSION|NAME`
- gene/locus IDs may be available as `GN=...`
- annotation columns come from a UniProt-style TSV download

To support another data source or organism, users should verify:

1. the annotation table contains a usable accession column
2. the FASTA headers contain matching accessions
3. the FASTA headers contain usable gene/locus IDs if renaming is enabled
4. the configured filtering terms are biologically appropriate
5. downstream pooling IDs match the IDs written to `candidate_proteins.fasta`

---

# Developer Notes

## Why Dynamic Filters Are Preferred

The dynamic filter system is easier to maintain than hard-coded Boolean functions.

Instead of adding code like:

```python
def is_secreted(row, text):
    ...
```

developers or users can add:

```yaml
filters:
  secreted:
    reason: secreted
    terms:
      - secreted
      - signal peptide
```

This reduces code changes, makes filtering behavior transparent, and allows project-specific filtering without modifying the pipeline.

---

## Recommended Future Improvement: Include and Exclude Filters

The current implementation treats all filters under `filters:` as exclusion filters.

A future extension could support separate sections:

```yaml
include_filters:
  cytosolic:
    terms:
      - cytosol
      - cytosolic

exclude_filters:
  ribosomal:
    terms:
      - ribosomal
      - ribosome
```

This would allow users to explicitly define both:

- proteins that must be retained
- proteins that must be excluded

For now, users should remember that all entries under `filters:` are exclusion rules.

---

## Recommended Future Improvement: More Precise Match Modes

The current dynamic matcher uses broad OR logic:

```text
terms OR gene_prefixes OR require_non_empty_column
```

A future version could support configurable match modes, for example:

```yaml
filters:
  membrane_bound:
    reason: membrane_bound
    match_mode: any
    terms:
      - transmembrane
    require_non_empty_column:
      - Transmembrane
```

or:

```yaml
filters:
  membrane_bound:
    reason: membrane_bound
    match_mode: all
    terms:
      - membrane
    require_non_empty_column:
      - Transmembrane
```

This would make filters more precise for ambiguous annotation categories.

---

## Recommended Future Improvement: Regex Support

Some filtering rules may eventually need regular expressions.

Example:

```yaml
filters:
  ribosomal:
    reason: ribosomal
    gene_regex:
      - "^rps[A-Z]$"
      - "^rpl[A-Z]$"
```

This is not required for the current workflow but may be useful for future organism-specific filtering.

