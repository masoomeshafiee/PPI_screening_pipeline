# Notes on Running the AlphaFold 3 Data Pipeline for Large-Scale MSA Caching on HPC

## 1. Context

AlphaFold 3 has two major computational stages:

1. **Data pipeline**
2. **Inference**

The **data pipeline** step performs Multiple Sequence Alignment (MSA) and template search for each sequence or chain in the input JSON file. This stage is CPU-bound and can be very time-consuming. In our benchmark, even a single sequence could take around 2–3 hours to complete the MSA/data-pipeline step.

For small jobs, this runtime may be acceptable. However, for large-scale screening, especially when processing hundreds or thousands of proteins, running the full data pipeline repeatedly is not practical or efficient.

To make large-scale screening more feasible, the recommended strategy is to separate the two AlphaFold 3 stages:

```bash
# Data-pipeline-only run
--run_data_pipeline=true
--run_inference=false
```

and later:

```bash
# Inference-only run
--run_data_pipeline=false
--run_inference=true
```

In this workflow, the first run generates the data-pipeline output, including MSA/template information. The second run reuses that output as input for inference, avoiding repeated MSA generation.

This separation is especially useful for high-throughput protein-protein interaction (PPI) or pooled-complex prediction, where the same proteins may appear in many different combinations. Instead of regenerating MSAs every time a protein appears in a pool or complex, the MSA can be generated once and reused.

The general strategy is:

1. Create one JSON file per unique protein.
2. Run the AlphaFold 3 data pipeline once for each protein.
3. Save the resulting `*_data.json` output as an MSA/data cache.
4. Incorporate the cached MSA/data information into future pooled or complex input JSON files.
5. Run later predictions with the data pipeline disabled and inference enabled.

This document summarizes the technical lessons learned while running this AlphaFold 3 data-pipeline caching workflow on an HPC cluster using SLURM array jobs and Apptainer.

The goal of the workflow was to precompute AlphaFold 3 data-pipeline outputs, especially MSA/template features, for many individual proteins. These cached outputs can later be reused for high-throughput PPI or pooled-complex predictions.

In this case, the workflow was tested on a filtered proteome containing approximately 3,000 proteins.

The benchmark SLURM array worked on a small test dataset of 10 proteins. However, the same resource settings did not scale well to the full production run. The production jobs were too slow, exceeded the 3-hour walltime limit, and were cancelled by SLURM.

This document explains why the benchmark worked, why the production run failed, and how to improve the workflow.

---

## 2. Original Production SLURM Configuration

The production workflow used a SLURM array job similar to:

```bash
#SBATCH --job-name=af3_msa_cache
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --array=11-900%10
#SBATCH --output=logs/slurm/msa_%A_%a.out
#SBATCH --error=logs/slurm/msa_%A_%a.err
```

Each array task processed one protein JSON file using:

```bash
python /app/alphafold/run_alphafold.py \
  --json_path="/root/af_input/${JSON_BASENAME}.json" \
  --model_dir=/root/models \
  --db_dir=/root/public_databases \
  --output_dir=/root/af_output \
  --run_data_pipeline=true \
  --run_inference=false
```

This means each array task was running only the AlphaFold 3 data pipeline, not GPU inference.

---

## 3. What the AlphaFold 3 Data Pipeline Does

AlphaFold 3 has two major stages.

### 3.1 Data Pipeline

The data pipeline:

- Performs genetic database search.
- Builds MSAs.
- Searches for templates.
- Runs mainly on CPU.
- Can be very time-consuming.
- Does not require a GPU.

The relevant flags are:

```bash
--run_data_pipeline=true
--run_inference=false
```

The official AlphaFold 3 documentation describes `--run_data_pipeline` as the genetic and template search stage. This part is CPU-only and time-consuming, and it can be run on a machine without a GPU.

### 3.2 Inference

The inference stage:

- Runs the AlphaFold 3 neural network model.
- Requires a GPU.
- Produces the final predicted structure outputs.

The relevant flags are:

```bash
--run_data_pipeline=false
--run_inference=true
```

Separating these two stages is useful because the CPU-heavy data pipeline and GPU-heavy inference stage have different resource requirements.

---

## 4. The Technical Problem Observed

The benchmark run completed successfully, but the larger production array failed to produce outputs for many proteins.

For example, the per-protein log stopped after the initial header:

```text
====================================
Array job ID: 63124373
Array task ID: 21
Protein: argG
JSON: json_inputs/argG.json
Start: Tue Jun 16 07:17:40 PM EDT 2026
Node: nc30505
====================================
```

It did not show:

```text
End
Completed
Output: ...
```

This happened because the script printed the final completion block only after the AlphaFold 3 command finished. In the failed production run, SLURM killed the jobs before the AlphaFold 3 command completed.

The SLURM accounting showed many tasks with:

```text
State: TIMEOUT
Elapsed: ~03:00:xx
```

The SLURM `.err` files showed messages like:

```text
CANCELLED ... DUE TO TIME LIMIT
```

Therefore, the immediate technical failure was:

```text
The jobs were not crashing because of missing paths or invalid JSON.
They were being killed by SLURM because the 3-hour walltime was too short.
```

---

## 5. Why the Benchmark Worked but the Production Run Failed

The benchmark answered one question:

```text
Can the AF3 data pipeline run successfully on this cluster with this container, model path, database path, and JSON format?
```

The answer was yes.

However, the production run tested a different question:

```text
Can hundreds or thousands of proteins be processed with 3 hours, 16 CPUs, 64 GB memory, and 10 concurrent array tasks?
```

The answer was no.

The benchmark likely worked because:

- It used only a small number of proteins.
- There was less shared database contention.
- The test proteins may have been easier or shorter.
- Only a few jobs were running at once.
- The successful test proteins finished within the time limit.

The production run failed because:

- Many proteins required more than 3 hours.
- Multiple Jackhmmer searches were launched per protein.
- Ten protein jobs were running at the same time.
- Each protein job performed heavy database searches.
- Memory usage was close to the 64 GB limit.
- Shared database I/O likely became a bottleneck.
- The 3-hour walltime was not enough for harder proteins.

This is a common HPC scaling issue: a command can work well on a small benchmark but fail or become inefficient when scaled to hundreds or thousands of jobs.

---

## 6. What Happens Inside One AlphaFold 3 Data-Pipeline Job

A single AlphaFold 3 data-pipeline job is not just one simple CPU process.

For one protein, AlphaFold 3 launches several genetic database searches. The logs showed Jackhmmer commands like:

```bash
jackhmmer --cpu 8 ... bfd-first_non_consensus_sequences.fasta
jackhmmer --cpu 8 ... mgy_clusters_2022_05.fa
jackhmmer --cpu 8 ... uniref90_2022_05.fa
jackhmmer --cpu 8 ... uniprot_all_2021_04.fa
```

So one AF3 data-pipeline job may launch approximately four Jackhmmer searches in parallel.

Each Jackhmmer search used:

```bash
--cpu 8
```

Therefore, one AF3 task may try to use roughly:

```text
4 Jackhmmer processes × 8 CPU threads = ~32 threads
```

This matters because the SLURM script requested only:

```bash
#SBATCH --cpus-per-task=16
```

So the job may have been under-requesting CPUs relative to what AlphaFold 3 was actually using internally.

The AlphaFold 3 performance documentation notes that genetic search can run across multiple databases in parallel and that CPU/core usage should be tuned according to Jackhmmer/Nhmmer CPU count, parallel shards, and database parallelism.

---

## 7. Important Concepts

### 7.1 SLURM Array Parallelism

This line:

```bash
#SBATCH --array=11-900%10
```

means:

```text
Run array tasks 11 through 900,
but keep at most 10 tasks running at the same time.
```

Each array task processes one protein.

With:

```bash
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --array=11-900%10
```

the total requested resources can be approximately:

```text
10 tasks × 16 CPUs = 160 CPUs
10 tasks × 64 GB = 640 GB memory
```

However, actual program behavior may use more threads than requested if the internal tool launches additional threaded subprocesses.

---

### 7.2 Thread-Level Parallelism

Jackhmmer itself is multi-threaded.

When Jackhmmer runs with:

```bash
--cpu 8
```

it can use up to 8 CPU threads.

If AlphaFold 3 launches four Jackhmmer processes at the same time, one AF3 task may use about 32 threads.

This is independent from the number of SLURM array tasks.

There are therefore two levels of parallelism:

```text
Workflow-level parallelism:
    How many proteins run at the same time?
    Controlled by the SLURM array % limit.

Within-job parallelism:
    How many threads/processes run inside one protein job?
    Controlled by AF3/Jackhmmer settings.
```

---

### 7.3 Oversubscription

Oversubscription happens when a program tries to use more CPU threads than the job requested from SLURM.

Example:

```text
SLURM allocation:
    16 CPUs

Actual internal usage:
    ~32 Jackhmmer threads
```

This is like booking 16 desks but having 32 people trying to work at the same time.

The job may still run, but it can become slower because the operating system has to time-share CPU cores between too many threads.

A more appropriate CPU request for the observed AF3 behavior may be:

```bash
#SBATCH --cpus-per-task=32
```

---

### 7.4 Database I/O

The AF3 data pipeline is not only CPU-bound. It is also database-I/O-heavy.

Jackhmmer scans very large sequence database files, such as:

```text
bfd-first_non_consensus_sequences.fasta
mgy_clusters_2022_05.fa
uniref90_2022_05.fa
uniprot_all_2021_04.fa
```

This requires:

```text
CPU       → sequence comparison
Memory    → intermediate data/results
I/O       → reading huge database files
```

If many jobs scan the same large databases at the same time, the shared filesystem or database storage can become a bottleneck.

This is true even if the jobs are running on different nodes.

Different nodes have separate CPUs and memory, but they may still read from the same shared storage system.

---

### 7.5 CPU-Bound vs I/O-Bound Work

A CPU-bound job spends most of its time computing.

An I/O-bound job spends much of its time waiting for data to be read or written.

AlphaFold 3 MSA generation is both:

```text
CPU-heavy + database-I/O-heavy
```

This means increasing parallelism does not always make the workflow faster.

Too much parallelism can cause database/filesystem contention and make every job slower.

---

## 8. Why Reducing Array Concurrency Can Help

At first, it may seem that if each array task runs on a different node, they should not affect each other.

This is partly true for CPU cores:

```text
CPU cores on node A do not directly slow CPU cores on node B.
```

But it is not fully true for shared database access.

With:

```bash
#SBATCH --array=11-900%10
```

and approximately four Jackhmmer searches per protein, the system may run:

```text
10 protein jobs × 4 Jackhmmer searches = ~40 database searches at once
```

Each search reads huge database files.

Even across different nodes, these jobs may compete for the same database storage bandwidth.

Therefore, reducing array concurrency from `%10` to `%3` or `%5` can improve stability and sometimes even improve total throughput.

The goal is not to maximize the number of simultaneous jobs. The goal is to maximize the number of successfully completed proteins per day.

---

## 9. Why More Parallelism Is Not Always Faster

Parallelism helps until a shared bottleneck becomes saturated.

A useful mental model:

```text
Too little parallelism:
    Resources are underused.

Good parallelism:
    Jobs run efficiently and throughput is high.

Too much parallelism:
    Jobs compete for CPU, memory, or I/O.
    Individual jobs slow down.
    Walltime is exceeded.
    Outputs are not produced.
```

For this workflow, too much parallelism can cause:

- CPU oversubscription inside each job.
- Shared database I/O contention.
- Memory pressure.
- Longer Jackhmmer runtime.
- SLURM timeouts.

---

## 10. Interpreting the Logs

The most useful diagnostic command was:

```bash
sacct -j <JOB_ID> --format=JobID,JobName%20,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocCPUS
```

This showed that many tasks ended with:

```text
TIMEOUT
```

The `.err` files contained AlphaFold 3 and Jackhmmer progress logs.

Useful patterns include:

```bash
grep -R "Finished Jackhmmer" logs/slurm/msa_<JOBID>_*.err
grep -R "Getting protein MSAs took" logs/slurm/msa_<JOBID>_*.err
grep -R "DUE TO TIME LIMIT" logs/slurm/msa_<JOBID>_*.err
```

The per-protein logs were less informative because the script printed the completion message only after AF3 finished. Since the jobs were killed during AF3 execution, the final messages were never written.

---

## 11. Recommended Immediate Fixes

### 11.1 Increase Walltime

The original time limit was:

```bash
#SBATCH --time=03:00:00
```

This was too short.

A safer setting is:

```bash
#SBATCH --time=12:00:00
```

For very long proteins, even longer may be needed.

However, requesting a longer walltime may increase queue time. A practical compromise is to first test:

```bash
#SBATCH --time=08:00:00
```

with enough memory and reduced concurrency, then increase the time limit only if needed.

---

### 11.2 Increase CPU Allocation

The original CPU request was:

```bash
#SBATCH --cpus-per-task=16
```

But AF3 was launching multiple Jackhmmer processes with `--cpu 8`.

Recommended:

```bash
#SBATCH --cpus-per-task=32
```

This better matches the observed internal parallelism.

---

### 11.3 Increase Memory

The original memory request was:

```bash
#SBATCH --mem=64G
```

However, observed memory usage was often close to 64 GB.

Recommended:

```bash
#SBATCH --mem=96G
```

or safer:

```bash
#SBATCH --mem=128G
```

A practical starting point may be:

```bash
#SBATCH --mem=96G
```

If jobs still fail or approach the memory limit, increase to 128 GB.

---

### 11.4 Reduce Array Concurrency Initially

The original array limit was:

```bash
#SBATCH --array=11-900%10
```

For debugging and stable production:

```bash
#SBATCH --array=11-900%3
```

or:

```bash
#SBATCH --array=11-900%5
```

After confirming successful completion, increase gradually.

---

## 12. Recommended Safer Production Settings

A conservative production configuration is:

```bash
#SBATCH --job-name=af3_msa_cache
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --array=11-900%3
#SBATCH --output=/home/masous97/projects/def-rod/masous97/pooled_ppi/inputs/msa_cache/logs/slurm/msa_%A_%a.out
#SBATCH --error=/home/masous97/projects/def-rod/masous97/pooled_ppi/inputs/msa_cache/logs/slurm/msa_%A_%a.err
```

However, this configuration may increase queue time because it requests more CPUs, more memory, and longer walltime.

A more practical first test may be:

```bash
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --array=11-100%3
```

If this succeeds, scale gradually. If jobs still timeout or approach the memory limit, increase to 12 hours and/or 128 GB.

Using absolute output/error paths is recommended because relative SLURM paths depend on the directory where `sbatch` is launched.

---

## 13. Recommended Script Improvements

Add explicit logging before AF3 starts:

```bash
echo "Running AF3 data pipeline for ${JSON_BASENAME}" | tee -a "$PROTEIN_LOG"
echo "Command start: $(date)" | tee -a "$PROTEIN_LOG"
```

Add a trap for normal command failures:

```bash
trap 'echo "FAILED at line $LINENO with exit code $? at $(date)" | tee -a "$PROTEIN_LOG"' ERR
```

Note: if SLURM kills the job because of walltime, the trap may not always have time to write a clean failure message. The SLURM `.err` file remains the most reliable source for timeout messages.

Also add a check for missing JSON files:

```bash
if [ ! -f "$MSA_JOB_DIR/json_inputs/${JSON_BASENAME}.json" ]; then
  echo "ERROR: JSON file not found: $MSA_JOB_DIR/json_inputs/${JSON_BASENAME}.json" | tee -a "$PROTEIN_LOG"
  exit 1
fi
```

---

## 14. Database Location and I/O Optimization

The workflow initially used AF3 databases from CVMFS:

```bash
DB_DIR=/cvmfs/bio.data.computecanada.ca/content/databases/Core/alphafold3_dbs/2025_01_21
```

This is convenient, but it may be slow for large production runs because many jobs repeatedly scan huge files from shared infrastructure.

A likely optimization is to copy the databases once to `$SCRATCH` and use that path instead:

```bash
DB_DIR=$SCRATCH/alphafold3_dbs/2025_01_21
```

The Digital Research Alliance of Canada AlphaFold3 documentation recommends using `$SCRATCH` for AlphaFold3 database storage on Alliance systems.

Example one-time copy:

```bash
mkdir -p $SCRATCH/alphafold3_dbs

rsync -avh --progress \
  /cvmfs/bio.data.computecanada.ca/content/databases/Core/alphafold3_dbs/2025_01_21/ \
  $SCRATCH/alphafold3_dbs/2025_01_21/
```

This command copies the AlphaFold 3 database from the shared CVMFS path to your personal `$SCRATCH` storage area.

Breakdown of the command:

- `rsync`: A fast and reliable tool for copying files locally or remotely.
- `-a`: Archive mode; preserves permissions, timestamps, symlinks, and directory structure.
- `-v`: Verbose mode; prints transferred files.
- `-h`: Human-readable output; shows file sizes in readable units.
- `--progress`: Shows transfer progress, speed, and estimated time.
- `/cvmfs/...`: Source directory containing the AlphaFold 3 database files.
- `$SCRATCH/...`: Destination directory on scratch storage.

Then update the SLURM script:

```bash
DB_DIR=$SCRATCH/alphafold3_dbs/2025_01_21
```

Important: do **not** copy the full database at the beginning of every array task. That would create a huge amount of repeated I/O and make the problem worse.

---

## 15. Benchmarking CVMFS vs Scratch

To test whether database location improves speed, run a controlled benchmark.

Use the same set of proteins and the same resource settings.

### Test A: CVMFS database

```bash
DB_DIR=/cvmfs/bio.data.computecanada.ca/content/databases/Core/alphafold3_dbs/2025_01_21
```

### Test B: Scratch database

```bash
DB_DIR=$SCRATCH/alphafold3_dbs/2025_01_21
```

Use:

```bash
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --time=08:00:00
#SBATCH --array=11-20%1
```

or:

```bash
#SBATCH --array=11-20%2
```

Then compare:

```bash
grep -R "Finished Jackhmmer" $MSA_JOB_DIR/logs/slurm/msa_<JOBID>_*.err
grep -R "Getting protein MSAs took" $MSA_JOB_DIR/logs/slurm/msa_<JOBID>_*.err
```

This gives direct evidence of whether `$SCRATCH` improves MSA-generation time.

---

## 16. Caching and Reusing MSA Outputs

For high-throughput PPI or pooled-complex prediction, the biggest workflow-level optimization is to avoid recomputing MSAs for the same protein many times.

A bad workflow is:

```text
For every complex:
    run full AF3 data pipeline again
    regenerate MSA for bait
    regenerate MSA for prey
    run inference
```

This wastes enormous time if the same proteins appear in many complexes.

A better workflow is:

```text
Step 1:
    Run AF3 data pipeline once per unique protein.
    Save each *_data.json output.

Step 2:
    Build complex/pool JSONs using precomputed MSA/template information.

Step 3:
    Run inference with:
        --run_data_pipeline=false
        --run_inference=true
```

AlphaFold 3 input documentation supports custom MSA fields for protein and RNA chains.

This is especially important for pooled PPI screening because the same bait or prey proteins are reused across many predictions.

---

## 17. Why AlphaFold Server May Be Faster

AlphaFold Server may feel much faster because it likely runs on infrastructure optimized specifically for this workload.

Possible reasons include:

- Faster database storage.
- Cached database search results.
- Highly optimized internal scheduling.
- Pre-indexed or optimized search infrastructure.
- Different backend behavior.
- Large-scale resources tuned for AF3.
- Less overhead visible to the user.

A local HPC run using Jackhmmer against huge database files on shared storage may be slower, especially if many array jobs run concurrently.

Therefore, the server runtime is not directly comparable to a local HPC production run.

However, the comparison is still useful because it suggests that local performance can often be improved with better database placement, CPU allocation, caching, and workflow design.

---

## 18. Sorting Proteins by Expected Runtime

Not all proteins take the same amount of time.

Runtime can depend on:

- Protein length.
- Sequence composition.
- Number of homologs found.
- Database search complexity.
- Template search results.
- Filesystem/database load.
- Node performance.

A useful optimization is to split proteins into bins:

```text
short proteins:
    lower walltime, less memory

medium proteins:
    moderate walltime and memory

long proteins:
    higher walltime and memory

very long proteins:
    special jobs with more time/memory
```

Example:

```text
short:      4h,  64G
medium:     8h,  96G
long:      12h, 128G
very long: 24h, 128G+
```

This prevents over-allocating resources for short proteins while giving long proteins enough time to complete.

---

## 19. Throughput vs Runtime

There are two different performance goals.

### 19.1 Runtime per Protein

Runtime per protein means how long one protein takes.

Example:

```text
protein A finishes in 4 hours
```

### 19.2 Throughput

Throughput means how many proteins finish per day.

Example:

```text
60 proteins/day completed successfully
```

Increasing array concurrency may improve throughput up to a point. After that, shared I/O contention and oversubscription can slow each job down and reduce successful completions.

The best configuration is the one that maximizes completed outputs per day, not necessarily the one with the highest number of simultaneous jobs.

---

## 20. Suggested Optimization Strategy

Use an empirical strategy rather than guessing.

### Step 1: Stabilize the Workflow

Start with a small production-like subset:

```bash
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --array=11-50%3
```

Confirm that outputs are produced.

If jobs still timeout or approach memory limits, increase to:

```bash
#SBATCH --time=12:00:00
#SBATCH --mem=128G
```

---

### Step 2: Compare Database Locations

Run the same 10 proteins with:

```text
CVMFS database
```

and:

```text
$SCRATCH database
```

Compare Jackhmmer times.

---

### Step 3: Tune Concurrency

Try:

```text
%3
%5
%8
```

Compare:

- Number of completed proteins.
- Average elapsed time.
- Jackhmmer runtime.
- Timeout rate.
- Memory usage.

---

### Step 4: Tune Resource Bins

Split proteins by length or observed runtime.

Use smaller resources for short proteins and larger resources for long proteins.

---

### Step 5: Ensure Downstream MSA Reuse

Do not run the AF3 data pipeline again for every pooled complex if precomputed MSAs are available.

Use precomputed data/MSA where possible and run inference-only jobs later.

---

## 21. Useful Monitoring Commands

Check job state:

```bash
squeue -u $USER
```

Check accounting:

```bash
sacct -j <JOB_ID> --format=JobID,JobName%20,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocCPUS
```

Count completed AF3 data outputs:

```bash
find $MSA_JOB_DIR/outputs -name "*_data.json" | wc -l
```

Find timeout messages:

```bash
grep -R "DUE TO TIME LIMIT" $MSA_JOB_DIR/logs/slurm/msa_<JOBID>_*.err
```

Inspect Jackhmmer runtimes:

```bash
grep -R "Finished Jackhmmer" $MSA_JOB_DIR/logs/slurm/msa_<JOBID>_*.err
```

Inspect total MSA time:

```bash
grep -R "Getting protein MSAs took" $MSA_JOB_DIR/logs/slurm/msa_<JOBID>_*.err
```

Find incomplete output directories:

```bash
find $MSA_JOB_DIR/outputs -mindepth 1 -maxdepth 1 -type d | wc -l
find $MSA_JOB_DIR/outputs -name "*_data.json" | wc -l
```

---

## 22. Recommended Final Template for the MSA Cache Job

```bash
#!/bin/bash
#SBATCH --job-name=af3_msa_cache
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --array=11-900%3
#SBATCH --output=/home/masous97/projects/def-rod/masous97/pooled_ppi/inputs/msa_cache/logs/slurm/msa_%A_%a.out
#SBATCH --error=/home/masous97/projects/def-rod/masous97/pooled_ppi/inputs/msa_cache/logs/slurm/msa_%A_%a.err

set -euo pipefail

module load apptainer

PROJECT_DIR=$HOME/projects/def-rod/masous97/pooled_ppi
MSA_JOB_DIR=$PROJECT_DIR/inputs/msa_cache

CONTAINER=$PROJECT_DIR/containers/alphafold3.sif

# Prefer $SCRATCH for production if the database has been copied there.
# Otherwise use the CVMFS path for testing/convenience.
DB_DIR=$SCRATCH/alphafold3_dbs/2025_01_21
# DB_DIR=/cvmfs/bio.data.computecanada.ca/content/databases/Core/alphafold3_dbs/2025_01_21

mkdir -p "$MSA_JOB_DIR/outputs"
mkdir -p "$MSA_JOB_DIR/logs/slurm"
mkdir -p "$MSA_JOB_DIR/logs/proteins"

JSON_REL_PATH=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$MSA_JOB_DIR/json_list.txt")

if [ -z "$JSON_REL_PATH" ]; then
  echo "No JSON found for array task ${SLURM_ARRAY_TASK_ID}"
  exit 1
fi

JSON_BASENAME=$(basename "$JSON_REL_PATH" .json)
PROTEIN_LOG="$MSA_JOB_DIR/logs/proteins/${JSON_BASENAME}.log"

trap 'echo "FAILED at line $LINENO with exit code $? at $(date)" | tee -a "$PROTEIN_LOG"' ERR

{
  echo "===================================="
  echo "Array job ID: ${SLURM_ARRAY_JOB_ID}"
  echo "Array task ID: ${SLURM_ARRAY_TASK_ID}"
  echo "Protein: ${JSON_BASENAME}"
  echo "JSON: ${JSON_REL_PATH}"
  echo "Start: $(date)"
  echo "Node: $(hostname)"
  echo "===================================="
} | tee -a "$PROTEIN_LOG"

if [ ! -f "$MSA_JOB_DIR/json_inputs/${JSON_BASENAME}.json" ]; then
  echo "ERROR: JSON file not found: $MSA_JOB_DIR/json_inputs/${JSON_BASENAME}.json" | tee -a "$PROTEIN_LOG"
  exit 1
fi

if [ -f "$MSA_JOB_DIR/outputs/$JSON_BASENAME/${JSON_BASENAME}_data.json" ]; then
  echo "Skipping ${JSON_BASENAME}: data JSON already exists." | tee -a "$PROTEIN_LOG"
  exit 0
fi

echo "Running AF3 data pipeline for ${JSON_BASENAME}" | tee -a "$PROTEIN_LOG"
echo "Command start: $(date)" | tee -a "$PROTEIN_LOG"

apptainer exec \
  --bind "$MSA_JOB_DIR/json_inputs:/root/af_input" \
  --bind "$MSA_JOB_DIR/outputs:/root/af_output" \
  --bind "$PROJECT_DIR/models:/root/models" \
  --bind "$DB_DIR:/root/public_databases" \
  "$CONTAINER" \
  python /app/alphafold/run_alphafold.py \
    --json_path="/root/af_input/${JSON_BASENAME}.json" \
    --model_dir=/root/models \
    --db_dir=/root/public_databases \
    --output_dir=/root/af_output \
    --run_data_pipeline=true \
    --run_inference=false

{
  echo "End: $(date)"
  echo "Completed: ${JSON_BASENAME}"
  echo "Output: $MSA_JOB_DIR/outputs/$JSON_BASENAME/${JSON_BASENAME}_data.json"
} | tee -a "$PROTEIN_LOG"
```

For more conservative production runs, use:

```bash
#SBATCH --time=12:00:00
#SBATCH --mem=128G
```

---

## 23. Key Takeaways

1. The production job failed because many tasks timed out after 3 hours.
2. The benchmark worked because it tested a smaller and less demanding workload.
3. One AF3 data-pipeline task internally launches multiple Jackhmmer searches.
4. Each Jackhmmer search can use multiple CPU threads.
5. Requesting 16 CPUs may be too low if AF3 uses approximately 32 threads.
6. Running many array tasks simultaneously can create shared database I/O contention.
7. CVMFS is convenient but may not be optimal for large production database scans.
8. Copying databases once to `$SCRATCH` may improve performance.
9. The best optimization for pooled PPI screening is MSA reuse.
10. Optimize for successful completed outputs per day, not maximum simultaneous jobs.
11. Start with a smaller production-like benchmark before scaling to thousands of proteins.

---

## 24. Practical Next Step

Before launching the full production run again, run a controlled benchmark:

```text
10–20 proteins
32 CPUs
96 GB memory
8 hours
array concurrency %1 or %2
CVMFS database
```

Then repeat the same benchmark with:

```text
$SCRATCH database
```

Compare Jackhmmer runtimes and total MSA times.

After that, choose the best database path and gradually increase array concurrency:

```text
%3 → %5 → %8
```

Only scale to the full production range once a smaller production-style test completes reliably.

---

## 25. Related Work: AF_Cache

A recent related workflow is **AF_Cache**, which was developed to improve large-scale AlphaFold-based protein-protein interaction prediction.

AF_Cache focuses on reducing repeated computational work by combining ideas such as:

- GPU-accelerated MSA generation with MMseqs2.
- Feature caching to avoid redundant alignment computations.
- Sequence length bucketing to reduce repeated compilation overhead.
- Workflow-level optimization for high-throughput PPI prediction.

This is conceptually aligned with the goal of this workflow: avoid recomputing expensive MSA/data-pipeline outputs when the same proteins are reused across many predictions.

References:

- AF_Cache paper: https://arxiv.org/abs/2606.04566
- AF_Cache GitHub repository: https://github.com/clami66/AF_cache

This may be useful to study later if the official AF3 Jackhmmer-based pipeline remains too slow even after improving resource allocation, database placement, and MSA reuse.

---

## 26. References

- AlphaFold 3 GitHub repository: https://github.com/google-deepmind/alphafold3
- AlphaFold 3 performance documentation: https://github.com/google-deepmind/alphafold3/blob/main/docs/performance.md
- AlphaFold 3 input documentation: https://github.com/google-deepmind/alphafold3/blob/main/docs/input.md
- Digital Research Alliance of Canada AlphaFold3 documentation: https://docs.alliancecan.ca/wiki/AlphaFold3
- AF_Cache paper: https://arxiv.org/abs/2606.04566
- AF_Cache GitHub repository: https://github.com/clami66/AF_cache
