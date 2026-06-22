from pathlib import Path
import argparse
import re

import pandas as pd
import yaml
from Bio import SeqIO


def load_config(config_path: str | Path) -> dict:
    """Load YAML configuration file."""
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def normalize_text(value) -> str:
    """Convert missing values to empty string and lowercase everything."""
    if pd.isna(value):
        return ""
    return str(value).lower()


def combined_annotation_text(row: pd.Series, text_columns: list[str]) -> str:
    """Combine all useful annotation fields into one searchable string."""
    values = []

    for col in text_columns:
        if col in row:
            values.append(normalize_text(row[col]))

    return " ".join(values)


def get_gene_names(row: pd.Series, gene_names_col: str) -> list[str]:
    """Extract gene names from UniProt gene-name field."""
    gene_text = normalize_text(row.get(gene_names_col, ""))
    return gene_text.split()


def has_any_term(text: str, terms: list[str]) -> bool:
    """Return True if any configured term is found in the annotation text."""
    return any(term.lower() in text for term in terms)


# -------------------------------- predifined filtering functions --------------------------------

# def is_ribosomal(row: pd.Series, text: str, config: dict) -> bool:
#     ribosomal_config = config["filters"]["ribosomal"]

#     gene_names_col = config["columns"]["gene_names"]
#     genes = get_gene_names(row, gene_names_col)

#     prefixes = tuple(ribosomal_config.get("gene_prefixes", []))
#     terms = ribosomal_config.get("terms", [])

#     has_ribosomal_gene_prefix = any(
#         gene.startswith(prefixes)
#         for gene in genes
#     )

#     return has_ribosomal_gene_prefix or has_any_term(text, terms)


# def is_membrane_bound(row: pd.Series, text: str, config: dict) -> bool:
#     membrane_config = config["filters"]["membrane_bound"]

#     transmembrane_col = membrane_config.get("transmembrane_column", "Transmembrane")
#     transmembrane_text = normalize_text(row.get(transmembrane_col, ""))

#     terms = membrane_config.get("terms", [])
#     has_transmembrane_feature = bool(transmembrane_text.strip())

#     return has_transmembrane_feature or has_any_term(text, terms)


# def is_outer_membrane_or_cell_wall(text: str, config: dict) -> bool:
#     filter_config = config["filters"]["outer_membrane_or_cell_wall"]
#     terms = filter_config.get("terms", [])

#     return has_any_term(text, terms)


# def is_periplasmic(text: str, config: dict) -> bool:
#     filter_config = config["filters"]["periplasmic"]
#     terms = filter_config.get("terms", [])

#     return has_any_term(text, terms)


# def get_exclusion_reasons_predifined(row: pd.Series, config: dict) -> str:
#     text_columns = config["text_columns"]
#     text = combined_annotation_text(row, text_columns)

#     reasons = []

#     if is_ribosomal(row, text, config):
#         reasons.append(config["filters"]["ribosomal"]["reason"])

#     if is_membrane_bound(row, text, config):
#         reasons.append(config["filters"]["membrane_bound"]["reason"])

#     if is_outer_membrane_or_cell_wall(text, config):
#         reasons.append(config["filters"]["outer_membrane_or_cell_wall"]["reason"])

#     if is_periplasmic(text, config):
#         reasons.append(config["filters"]["periplasmic"]["reason"])

#     return ";".join(sorted(set(reasons)))


# -------------------------------- dynamic filtering functions --------------------------------

def has_any_term(text: str, terms: list[str]) -> bool:
    """Return True if any configured term is found in the combined annotation text."""
    return any(term.lower() in text for term in terms)


def has_gene_prefix(row: pd.Series, gene_prefixes: list[str], gene_names_col: str) -> bool:
    """Return True if any gene name starts with one of the configured prefixes."""
    if not gene_prefixes:
        return False

    genes = get_gene_names(row, gene_names_col)
    prefixes = tuple(prefix.lower() for prefix in gene_prefixes)

    return any(gene.lower().startswith(prefixes) for gene in genes)


def has_required_non_empty_column(row: pd.Series, columns: list[str]) -> bool:
    """
    Return True if any configured column exists and has a non-empty value.

    Example:
    require_non_empty_column:
      - Transmembrane

    This is useful for excluding proteins with explicit UniProt transmembrane features.
    """
    if not columns:
        return False

    for col in columns:
        value = normalize_text(row.get(col, ""))
        if value.strip():
            return True

    return False


def matches_filter(
    row: pd.Series,
    text: str,
    filter_config: dict,
    config: dict,
) -> bool:
    """
    Generic filter matcher.

    A protein matches a filter if it satisfies at least one configured rule:
    - any annotation term is found
    - any gene name starts with a configured prefix
    - any configured required column is non-empty
    """
    gene_names_col = config["columns"]["gene_names"]

    terms = filter_config.get("terms", [])
    gene_prefixes = filter_config.get("gene_prefixes", [])
    required_columns = filter_config.get("require_non_empty_column", [])

    term_match = has_any_term(text, terms)
    prefix_match = has_gene_prefix(row, gene_prefixes, gene_names_col)
    non_empty_column_match = has_required_non_empty_column(row, required_columns)
    
    return term_match or prefix_match or non_empty_column_match


def get_exclusion_reasons(row: pd.Series, config: dict) -> str:
    """
    Apply all filters defined in the config dynamically.

    Any new filter added under config['filters'] will automatically be applied.
    """
    text_columns = config["text_columns"]
    text = combined_annotation_text(row, text_columns)

    reasons = []

    for filter_name, filter_config in config.get("filters", {}).items():
        if matches_filter(row, text, filter_config, config):
            reason = filter_config.get("reason", filter_name)
            reasons.append(reason)

    return ";".join(sorted(set(reasons)))

def extract_uniprot_accession_from_fasta_id(record_id: str) -> str:
    """
    UniProt FASTA IDs usually look like:
    sp|B8H358|CTRA_CAUVN
    tr|A0A...|...

    This function extracts B8H358.
    """
    parts = record_id.split("|")

    if len(parts) >= 2:
        return parts[1]

    return record_id


def extract_gene_name_from_description(description: str) -> str | None:
    """Extract GN= gene name from UniProt FASTA description."""
    match = re.search(r"\bGN=([A-Za-z0-9_.-]+)", description)

    if not match:
        return None

    return match.group(1)


def export_candidate_fasta(
    candidate_ids: set[str],
    fasta_file: Path,
    candidate_fasta: Path,
    config: dict,
) -> int:
    """Export FASTA records matching kept UniProt accessions."""
    records_to_keep = []

    fasta_config = config.get("fasta", {})


    rename_header = fasta_config.get("rename_header_to_gene_name", True)
    require_gene_name = fasta_config.get("require_gene_name", True)
    fasta_format = fasta_config.get("parser_format", "fasta")

    print(f"Reading FASTA file: {fasta_file}")
    print(f"Using FASTA parser: {fasta_format}")
    for record in SeqIO.parse(fasta_file, fasta_format):
        accession = extract_uniprot_accession_from_fasta_id(record.id)

        if accession not in candidate_ids:
            continue

        if rename_header:
            gene_id = extract_gene_name_from_description(record.description)

            if gene_id is None:
                if require_gene_name:
                    raise ValueError(
                        f"Could not find GN= in FASTA header: {record.description}"
                    )

                gene_id = accession

            record.id = gene_id
            record.name = gene_id
            record.description = gene_id

        records_to_keep.append(record)

    SeqIO.write(records_to_keep, candidate_fasta, "fasta")

    return len(records_to_keep)


def validate_config_columns(df: pd.DataFrame, config: dict) -> None:
    """Validate that required configured columns exist in the annotation file."""
    accession_col = config["columns"]["accession"]

    if accession_col not in df.columns:
        raise ValueError(
            f"Expected annotation table to contain accession column: '{accession_col}'"
        )

    missing_text_columns = [
        col for col in config["text_columns"]
        if col not in df.columns
    ]

    if missing_text_columns:
        print("Warning: the following configured text columns were not found:")
        for col in missing_text_columns:
            print(f"- {col}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter a UniProt proteome annotation table and export candidate FASTA."
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML config file.",
    )

    args = parser.parse_args()

    config = load_config(args.config)

    annotation_file = Path(config["input"]["annotation_file"])
    fasta_file = Path(config["input"]["fasta_file"])

    output_dir = Path(config["output"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    all_output = output_dir / config["output"]["all_output"]
    candidate_csv = output_dir / config["output"]["candidate_csv"]
    excluded_csv = output_dir / config["output"]["excluded_csv"]
    candidate_fasta = output_dir / config["output"]["candidate_fasta"]

    df = pd.read_csv(annotation_file, sep="\t")

    validate_config_columns(df, config)

    accession_col = config["columns"]["accession"]

    df["exclusion_reason"] = df.apply(
        lambda row: get_exclusion_reasons(row, config),
        axis=1,
    )

    df["filter_status"] = df["exclusion_reason"].apply(
        lambda reason: "keep" if reason == "" else "exclude"
    )

    kept = df[df["filter_status"] == "keep"].copy()
    excluded = df[df["filter_status"] == "exclude"].copy()

    df.to_csv(all_output, index=False)
    kept.to_csv(candidate_csv, index=False)
    excluded.to_csv(excluded_csv, index=False)

    candidate_ids = set(kept[accession_col].astype(str))

    fasta_count = export_candidate_fasta(
        candidate_ids=candidate_ids,
        fasta_file=fasta_file,
        candidate_fasta=candidate_fasta,
        config=config,
    )

    print("Filtering complete.")
    print(f"Total proteins: {len(df)}")
    print(f"Kept candidates: {len(kept)}")
    print(f"Excluded proteins: {len(excluded)}")
    print(f"FASTA records exported: {fasta_count}")

    print("\nOutput files:")
    print(f"- {all_output}")
    print(f"- {candidate_csv}")
    print(f"- {excluded_csv}")
    print(f"- {candidate_fasta}")


if __name__ == "__main__":
    main()