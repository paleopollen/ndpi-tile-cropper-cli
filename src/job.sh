#!/bin/bash
#SBATCH --job-name="PALYIM_TADP_dirs_4_7_ntcp_v1.1.1_s_2048_l_256_20250620"
#SBATCH --partition=cpu
#SBATCH --mem-per-cpu=2G
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=2  # Reduced from 4 to avoid JVM conflicts
#SBATCH --cpus-per-task=8   # spread out to use 1 core per numa, set to 64 if tasks is 1
#SBATCH --constraint="scratch"
#SBATCH --account=bdar-delta-cpu    # <- match to a "Project" returned by the "accounts" command
##SBATCH --exclusive  # dedicated node for this job
#SBATCH --no-requeue
#SBATCH -t 48:00:00
#SBATCH -e slurm-%j-%x.err
#SBATCH -o slurm-%j-%x.out
#SBATCH --mail-user=sandeeps@illinois.edu
#SBATCH --mail-type="BEGIN,END" # See sbatch or srun man pages for more email options

export OMP_NUM_THREADS=1  # 1 if code is not multithreaded, otherwise set to the number of CPUs allocated per task.
cd /projects/bdar/sandeeps/git/ndpi-tile-cropper-cli/src

# Function to run with retry logic using the simple parallel CLI
run_with_retry() {
    local max_retries=3
    local retry_count=0
    local success=false
    
    while [ $retry_count -lt $max_retries ] && [ "$success" = false ]; do
        if [ $retry_count -gt 0 ]; then
            echo "Retry attempt $retry_count for $1"
            sleep $((RANDOM % 10 + 5))  # Random delay between 5-15 seconds
        fi
        
        if srun --ntasks=1 --cpus-per-task=$SLURM_CPUS_PER_TASK /usr/bin/apptainer run --bind /work/hdd/bdar/data:/data ndpi-tile-cropper-parallel-pr-22.sif -d "$1" -o /data/TADP_TILE_CROPS -n 2 -s 2048 -l 256 -r 3; then
            success=true
            echo "Successfully processed $1"
        else
            retry_count=$((retry_count + 1))
            echo "Failed to process $1 (attempt $retry_count)"
        fi
    done
    
    if [ "$success" = false ]; then
        echo "Failed to process $1 after $max_retries attempts"
        return 1
    fi
    return 0
}

# Run each directory with retry logic and staggered starts
run_with_retry /data/TADP/4 &
sleep 10  # Stagger the starts to reduce JVM conflicts

run_with_retry /data/TADP/5 &
sleep 10

run_with_retry /data/TADP/6 &
sleep 10

run_with_retry /data/TADP/7 &
sleep 10

wait