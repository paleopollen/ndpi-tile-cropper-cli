# Site settings for the job templates. Copy to config.sh (git-ignored) and replace every CHANGEME.
# Sourced by submit.sh, cropper/common.sh and segmentation/common.sh.
# Any value can be overridden at submit time: VAR=value ./submit.sh <script>.

# SLURM accounts. submit.sh picks the GPU one for scripts or options that ask for --gpus.
SLURM_ACCOUNT_CPU=${SLURM_ACCOUNT_CPU:-CHANGEME-cpu-account}
SLURM_ACCOUNT_GPU=${SLURM_ACCOUNT_GPU:-CHANGEME-gpu-account}

# Shared folder for every test output and SLURM log (read-write, visible from compute nodes).
OUT_ROOT=${OUT_ROOT:-/CHANGEME/zarr-test/out}
# Shared folder holding the code and images (read-only for the jobs):
#   $WORK_ROOT/git/<repo>    clones on the branches under test (new code)
#   $WORK_ROOT/base/<repo>   git worktrees of those clones pinned to the base commits (G1a)
#   $WORK_ROOT/sif/          the two SIFs, each with its .sha256 and .pip-freeze.txt
#   $WORK_ROOT/jobs/         a copy of this jobs/ folder (jobs run helpers from the submit folder)
WORK_ROOT=${WORK_ROOT:-/CHANGEME/zarr-test}
CODE_ROOT=${CODE_ROOT:-$WORK_ROOT/git}
BASE_ROOT=${BASE_ROOT:-$WORK_ROOT/base}
SIF_DIR=${SIF_DIR:-$WORK_ROOT/sif}
CROPPER_SIF=${CROPPER_SIF:-$SIF_DIR/ndpi-tile-cropper-zarr.sif}
SEG_SIF=${SEG_SIF:-$SIF_DIR/post-processing-cli-sam-2-zarr.sif}

# Folders bound into the containers: outputs read-write, everything else read-only. List every filesystem the
# paths below live on (a symlinked data folder needs its target bound too). Node-local scratch is added by the jobs.
APPTAINER_BINDS=${APPTAINER_BINDS:-$OUT_ROOT,$WORK_ROOT:$WORK_ROOT:ro,/CHANGEME/data:/CHANGEME/data:ro}

# The two test slides (phase 1 used these). Quote every path: PAL file names contain spaces.
DATA_ROOT=${DATA_ROOT:-/CHANGEME/data}
TADP_SLIDE_NAME=54490_TADP1_232Q-2-69_L_2024_11_12_15_50_13
TADP_SLIDE_NDPI=${TADP_SLIDE_NDPI:-$DATA_ROOT/TADP_DATA/TADP_SLIDES/0/$TADP_SLIDE_NAME.ndpi}
PAL_SLIDE_NAME=PAL1999_B2_sample100_slide1          # the cropper truncates the file name at the first space
PAL_SLIDE_NDPI=${PAL_SLIDE_NDPI:-$DATA_ROOT/PAL1999_DATA/PAL1999_SLIDES/B2/$PAL_SLIDE_NAME - 2023-01-11 04.39.18.ndpi}

# Existing production outputs of the two slides, read only. Leave a value empty if there is none: the reported
# comparison against production is then skipped.
#   tiles:    the slide folder holding {x}x_{y}y/ and metadata.json
#   segments: the folder holding <slide>/metadata.json (and <slide>.csv)
TADP_PROD_PNG_DIR=${TADP_PROD_PNG_DIR-$DATA_ROOT/TADP_DATA/TADP_CROP_TILES/$TADP_SLIDE_NAME}
PAL_PROD_PNG_DIR=${PAL_PROD_PNG_DIR-$DATA_ROOT/PAL1999_DATA/PAL1999_TILE_CROPS/$PAL_SLIDE_NAME}
TADP_PROD_SEG_ROOT=${TADP_PROD_SEG_ROOT-/CHANGEME/TADP_SEGMENTS}
PAL_PROD_SEG_ROOT=${PAL_PROD_SEG_ROOT-$DATA_ROOT/PAL1999_DATA/PAL1999_SEGMENTS}

# SAM 2 checkpoint and config (only the config's basename is used; the copy packaged inside sam2 is loaded).
SAM2_CKPT=${SAM2_CKPT:-/CHANGEME/checkpoints/sam2_hiera_large.pt}
SAM2_CFG=${SAM2_CFG:-/CHANGEME/sam2_configs/sam2_hiera_l.yaml}

# Ground-truth annotations for the TADP slide. GT_CSV= (empty) runs without -g/-mt.
GT_CSV=${GT_CSV-$DATA_ROOT/TADP_DATA/TADP_ANNOTATIONS/Batch_ROI_Export_feb4.csv}

# Optional palyim-io source overlay: a checkout's src/ folder put on PYTHONPATH ahead of the image's copy, checked
# against PALYIM_IO_TAG. Phase 1 needed it (images had 0.1.0, the fix is in 0.1.1). Images that install palyim-io
# 0.1.2 or newer already have the fix: leave this empty.
PALYIM_IO_SRC=${PALYIM_IO_SRC-}
PALYIM_IO_TAG=${PALYIM_IO_TAG:-v0.1.1}
