# JVM Conflict Fixes for NDPI Tile Cropper

## Problem Description

When running the NDPI tile cropper in parallel mode using `job.sh`, you may encounter Java/Javabridge errors like:

```
org.libjpegturbo.turbojpeg.TJDecompressor.init()V
javabridge.jutil.JavaException: org.libjpegturbo.turbojpeg.TJDecompressor.init()V
```

This happens because:
1. Each subprocess starts its own JVM instance with `javabridge.start_vm()`
2. Multiple JVMs competing for the same resources cause conflicts
3. The Java library initialization fails when multiple processes access shared resources simultaneously

## Solutions Implemented

### 1. Improved Parallel Processing (`ndpi_tile_cropper_parallel_cli.py`)

**Changes made:**
- Switched from `ThreadPoolExecutor` to `ProcessPoolExecutor` for better isolation
- Reduced default number of processes from 8 to 4 to minimize conflicts
- Added retry logic with exponential backoff for JVM conflicts
- Added random delays between process starts to stagger JVM initialization
- Better error detection and handling for JVM-related failures
- Added timeout handling to prevent hanging processes

**New command-line options:**
- `--retry-attempts, -r`: Number of retry attempts for failed processing (default: 3)

### 2. Enhanced JVM Management (`ndpi_tile_cropper_cli.py`)

**Changes made:**
- Better JVM initialization error handling
- Improved cleanup in error scenarios
- More specific error messages for JVM conflicts
- Graceful handling of reader cleanup failures

### 3. Updated Job Script (`job.sh`)

**Changes made:**
- Reduced `--ntasks-per-node` from 4 to 2
- Added retry logic function with random delays
- Staggered process starts with 10-second delays
- Added the `-r 3` parameter for retry attempts

## Usage

### Running with Reduced Concurrency

```bash
# Use fewer parallel processes
python src/ndpi_tile_cropper_parallel_cli.py -d /path/to/ndpi/files -o /path/to/output -n 2 -r 3
```

### Using the Updated Job Script

```bash
# Submit the updated job script
sbatch src/job.sh
```

The script now includes:
- Retry logic for failed processes
- Staggered starts to reduce JVM conflicts
- Better error reporting

### Manual Retry Logic

If you still encounter issues, you can manually implement retry logic:

```bash
#!/bin/bash
max_retries=3
for attempt in {1..$max_retries}; do
    if python src/ndpi_tile_cropper_parallel_cli.py -d /path/to/files -o /path/to/output -n 2; then
        echo "Success on attempt $attempt"
        break
    else
        echo "Failed on attempt $attempt"
        sleep $((RANDOM % 30 + 10))  # Random delay 10-40 seconds
    fi
done
```

## Monitoring and Debugging

### Check for JVM Conflicts

Look for these patterns in your logs:
- `TJDecompressor` errors
- `javabridge` exceptions
- `JVM conflict detected` messages

### Log Analysis

The improved logging will now show:
- Specific JVM conflict detection
- Retry attempt information
- Success/failure counts for parallel processing

### Performance Considerations

**Trade-offs:**
- Reduced parallelism may increase total processing time
- Retry logic adds overhead but improves reliability
- Staggered starts reduce peak resource usage

**Recommended settings:**
- Start with 2-4 parallel processes
- Use 3 retry attempts
- Add 5-15 second delays between process starts

## Testing

Use the provided test script to verify the fixes:

```bash
# Update paths in test_jvm_fix.py first
python test_jvm_fix.py
```

## Alternative Solutions

If the above fixes don't resolve the issue, consider:

1. **Sequential Processing**: Process files one at a time
2. **Resource Limits**: Set JVM memory limits to prevent conflicts
3. **Container Isolation**: Use separate containers for each process
4. **Different JVM**: Try different JVM versions or configurations

## Troubleshooting

### Common Issues

1. **Still getting JVM errors**: Reduce the number of parallel processes further
2. **Processes hanging**: Check for timeout settings and resource limits
3. **Memory issues**: Monitor system memory usage during processing

### Debug Commands

```bash
# Check JVM processes
ps aux | grep java

# Monitor system resources
htop

# Check for file locks
lsof | grep ndpi
```

## Version History

- **v1.1.1**: Initial JVM conflict fixes
- Added retry logic and better error handling
- Reduced default parallelism
- Improved job script with staggered starts 