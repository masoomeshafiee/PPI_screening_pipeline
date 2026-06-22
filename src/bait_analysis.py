import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
import argparse
import yaml

# read the data in tsv, create a df and filter only the interaction of the protein of interest, sort them by the requested column or columns and return the filtered df
# -------------------------- Helpers --------------------------

def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)

# -------------------------- Main functions --------------------------
def filter_proteins(aggregated_result_file, protein_of_interest, sort_columns, output_dir):
    df_result = pd.read_csv(aggregated_result_file, sep="\t")
    df = df_result.copy()
    
    # filter the df to keep only the interactions of the protein of interest
    filtered_df = df[(df['protein_1'] == protein_of_interest) | (df['protein_2'] == protein_of_interest)]

    sorted_filtered_df = filtered_df.sort_values(by=sort_columns, ascending=False)

    output_file = f"filtered_{protein_of_interest}_{'_'.join(sort_columns)}.tsv"
    output_path = output_dir / output_file
    sorted_filtered_df.to_csv(output_path, sep="\t", index=False)
    print(f"Filtered results saved to {output_path}")


    return sorted_filtered_df


def plot_score_distribution(filtered_df, score_col, output_dir=None):
    plt.figure(figsize=(8, 5))

    plt.hist(filtered_df[score_col].dropna(), bins=30)

    plt.xlabel(score_col)
    plt.ylabel("Number of interactions")
    plt.title(f"Distribution of {score_col}")

    plt.tight_layout()
    if output_dir:
        plt.savefig(output_dir / f"score_distribution_{score_col}.svg", dpi=300)
    plt.show()




def add_partner_column(df, protein_of_interest, protein_1_col="protein_1", protein_2_col="protein_2"):
    """
    Add a column containing the interaction partner of the protein of interest.
    """
    df = df.copy()
    df["partner"] = df.apply(
        lambda row: row[protein_2_col] if row[protein_1_col] == protein_of_interest else row[protein_1_col],
        axis=1
    )
    return df

def plot_ranked_score_dots(filtered_df, protein_of_interest, score_col, protein_1_col="protein_1", protein_2_col="protein_2", top_n=50, output_dir=None):
    df = add_partner_column(filtered_df, protein_of_interest, protein_1_col, protein_2_col)
    df = df.sort_values(score_col, ascending=False).head(top_n)

    plt.figure(figsize=(10, 10))
    plt.scatter(df[score_col], df["partner"])

    plt.gca().invert_yaxis()
    plt.xlabel(score_col)
    plt.ylabel("Interaction partner")
    plt.title(f"Ranked interaction scores for {protein_of_interest}")

    plt.tight_layout()
    if output_dir:
        plt.savefig(output_dir / f"ranked_interaction_scores_{protein_of_interest}.svg", dpi=300)
    plt.show()
    # save the plot as a png file
    
def run_bait_analysis(config: dict) -> None:

    bait_config = config["bait_analysis"]

    aggregated_result_file =  Path(bait_config["aggregated_result_file"])
    protein_of_interest = bait_config["protein_of_interest"]
    sort_columns = bait_config["sort_columns"]
    score_col_for_plotting = bait_config["score_col_for_plotting"]
    top_n = bait_config.get("top_n", 50)
    protein_1_col = bait_config.get("protein_1_col", "protein_1")
    protein_2_col = bait_config.get("protein_2_col", "protein_2")


    output_dir = Path(bait_config.get("output_dir", aggregated_result_file.parent))
    output_dir.mkdir(parents=True, exist_ok=True)

    filtered_df = filter_proteins(aggregated_result_file, protein_of_interest, sort_columns, output_dir)


    plot_ranked_score_dots(
    filtered_df,
    protein_of_interest=protein_of_interest,
    score_col=score_col_for_plotting,
    protein_1_col=protein_1_col,
    protein_2_col=protein_2_col,
    top_n=top_n,
    output_dir=output_dir
    )



    plot_score_distribution(filtered_df, score_col_for_plotting, output_dir=output_dir)




if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()

    config = load_config(args.config)

    run_bait_analysis(config)