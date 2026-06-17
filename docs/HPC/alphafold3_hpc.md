# AlphaFold 3 on HPC

## Overview

This document describes how to run AlphaFold 3 on a High-Performance Computing (HPC) cluster and how it integrates with the pooled-PPI workflow.

This guide was developed and tested on the Narval cluster (Digital Research Alliance of Canada), but most concepts apply to other SLURM-based HPC systems.

---

# Big Picture

Running AlphaFold 3 on HPC follows the workflow:

```text
AlphaFold3 JSON
        ↓
SLURM Job Submission
        ↓
CPU / GPU Node Allocation
        ↓
Apptainer Container
        ↓
AlphaFold3 Execution
        ↓
Prediction Outputs
```

The pooled-PPI workflow and AlphaFold3 execution are separate steps.

---

# Local Machine vs HPC Responsibilities

## Local Machine

You:

* Filter proteins
* Generate pools
* Generate AF3 JSON files
* Validate inputs
* Download results
* Run pooled-PPI post-processing

---

## HPC

You:

* Upload JSON inputs
* Submit SLURM jobs
* Run AlphaFold3
* Download prediction outputs

---

# Core HPC Concepts

Before using AlphaFold 3 on HPC, it is useful to understand:

* SSH
* Linux filesystem
* SLURM
* CPU vs GPU resources
* Containers (Apptainer/Singularity)
* Modules
* Interactive allocations
* Bind mounts

---

# Step 1 — Connect to the Cluster

Example:

```bash
ssh your_username@narval.alliancecan.ca
```

Authentication typically requires:

* SSH key
* Multi-factor authentication (Duo)

---

# Step 2 — Understand Storage Locations

Typical HPC storage:

| Location | Purpose                 |
| -------- | ----------------------- |
| home     | Small permanent files   |
| project  | Shared research storage |
| scratch  | Fast temporary storage  |

Recommended usage:

```text
home
 └─ scripts, configs

project
 └─ model weights
 └─ containers
 └─ prediction outputs

scratch
 └─ temporary files
 └─ build directories
```

---

# Important

The login node is **not** where AlphaFold runs.

The login node should only be used for:

* Editing files
* Preparing scripts
* Uploading data
* Submitting jobs

Actual computation happens on allocated compute nodes.

---

# Step 3 — Create Project Structure

Example:

```bash
mkdir -p ~/projects/def-rod/af3_pool_ppi
cd ~/projects/def-rod/af3_pool_ppi

mkdir -p \
inputs \
outputs \
logs \
scripts \
models \
containers
```

Recommended structure:

```text
af3_pool_ppi/
├── inputs/ --> input json files created by the prepare step of our pipeline ( upload them)
├── outputs/ --> will be bind to the af3 container and the outputs will be save in here.
├── logs/ 
├── scripts/ --> the slurm_jobs.sh will rest here
├── models/ --> the .bin file tht has the weights requested from deep mind
└── containers/ --> the .sif file created from the uploaded docker image 
```

---

# Step 4 — AlphaFold 3 Model Weights

AlphaFold 3 model weights must be requested directly from Google DeepMind.

After downloading:

```bash
scp af3.bin.zst \
user@cluster:/path/to/models/
```

Example:

```text
models/
└── af3.bin
```

---

# Step 5 — AlphaFold Databases

On Narval, AlphaFold databases are already available through CVMFS.

Example:

```text
/cvmfs/bio.data.computecanada.ca/content/databases/Core/alphafold3_dbs/2025_01_21
```

These databases do not need to be downloaded.

Inside the container they are typically mounted as:

```text
/root/public_databases
```

Example bind:

```bash
--bind /cvmfs/.../alphafold3_dbs:/root/public_databases
```

---

# Step 6 — Build AlphaFold 3 Container

Docker cannot usually be run directly on HPC systems.

Instead:

1. Build Docker image locally
2. Upload image archive
3. Convert to Apptainer

---

## Build Docker Image

```bash
in your local terminal: 
git clone https://github.com/google-deepmind/alphafold3.git

docker build \
  --platform linux/amd64 \
  -t alphafold3 \
  -f docker/Dockerfile .
```

Save image:

```bash
docker save alphafold3:latest -o alphafold3.tar
```

Compress:

```bash
gzip alphafold3.tar
```

Upload:

```bash
scp alphafold3.tar.gz \
user@cluster:/path/to/containers/
```

---

## Convert to Apptainer

```bash
module load apptainer
```

Set temporary directories:

```bash
mkdir -p $SCRATCH/apptainer_cache
mkdir -p $SCRATCH/apptainer_tmp

export APPTAINER_CACHEDIR=$SCRATCH/apptainer_cache
export APPTAINER_TMPDIR=$SCRATCH/apptainer_tmp
```

Build:

```bash
apptainer build alphafold3.sif docker-archive://alphafold3.tar
```

---

# Step 7 — Test Container

Verify Python:

```bash
apptainer exec alphafold3.sif python --version
```

Verify JAX:

```bash
apptainer exec alphafold3.sif \
python -c "import jax; print(jax.__version__)"
```

---

# Step 8 — Test GPU Visibility

Before running AlphaFold, verify GPU access.

Example SLURM job:

```bash
#!/bin/bash
#SBATCH --job-name=af3_gpu_test
#SBATCH --time=00:10:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --gres=gpu:1

module load apptainer

apptainer exec --nv alphafold3.sif sh -c '
nvidia-smi
python -c "import jax; print(jax.devices())"
'
```

Expected output:

* GPU visible in `nvidia-smi`
* JAX detects CUDA device

---

# Running AlphaFold 3

AlphaFold 3 execution consists of two distinct stages.

---

# Stage 1 — Data Pipeline

Uses:

* CPU
* Memory
* Databases

Does not require GPU.

Produces:

```text
pool_00001_data.json
```

containing:

* unpaired MSA
* paired MSA
* templates
* sequence features

Example:

```bash
--run_data_pipeline=true
--run_inference=false
```

---

# Stage 2 — Inference

Uses:

* GPU

Consumes:

```text
pool_00001_data.json
```

Produces:

```text
model predictions
confidence scores
structures
```

Example:

```bash
--run_data_pipeline=false
--run_inference=true
```

---

# Important Observation

For pooled jobs, the major bottleneck is usually:

```text
MSA generation
```

not inference.

In many cases:

```text
Data pipeline
>>>
Inference
```

in runtime.

This becomes increasingly important for genome-scale screens.

---

# Common Errors

## Missing MSA

Example:

```text
Protein chain 1 is missing unpaired MSA
```

Cause:

Running inference directly on the original input JSON.

Solution:

Use:

```text
pool_00001_data.json
```

generated by the data pipeline.

---

## TPU Error

Example:

```text
Unable to initialize backend 'tpu'
```

This can usually be ignored.

AlphaFold attempts TPU initialization before falling back to GPU.

---

## NUMA Binding Errors

Example:

```text
hwloc_set_cpubind() failed
```

Usually harmless on many HPC systems.

---

# Large-Scale Screens

For small projects, standard AlphaFold execution is sufficient.

For genome-scale pooled screens, MSA generation becomes the dominant cost.

Recommended strategy:

```text
Generate MSAs once
       ↓
Cache MSAs
       ↓
Reuse MSAs in pooled jobs
       ↓
Run inference only
```

---

# MSA Caching Workflow

```text
candidate_proteins.fasta
          ↓
Create single-protein AF3 JSONs
          ↓
Run AF3 data pipeline only
          ↓
Extract unpaired MSA
          ↓
Build MSA cache
          ↓
Generate pooled AF3 JSONs
          ↓
Reuse cached MSAs
          ↓
Run inference only
```

Benefits:

* Eliminates repeated database searches
* Enables genome-scale screens
* Reduces total runtime dramatically

---

# Recommended Workflow

For most users:

```text
AlphaFold Server
```

For experts:

```text
HPC + MSA cache
```

The HPC workflow provides substantially more automation and scalability, but requires familiarity with:

* Linux
* SLURM
* Apptainer
* Resource allocation
* AlphaFold internals

For large-scale screens and detailed MSA caching workflows,
see `docs/alphafold3_optimization.md`


For small and medium projects, AlphaFold Server remains the simplest option.
