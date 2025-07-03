#!/usr/bin/env python3
"""
Test script to verify JVM conflict fixes for NDPI tile cropper.
This script tests the improved parallel processing with better error handling.
"""

import os
import sys
import subprocess
import time
import random
import logging

# Set up logging
logging.basicConfig(
    format='%(asctime)s %(levelname)-7s : %(name)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger("test_jvm_fix")

def test_single_process():
    """Test single process execution to ensure basic functionality works."""
    logger.info("Testing single process execution...")
    
    # You'll need to modify these paths for your test environment
    test_input_dir = "/path/to/test/ndpi/files"  # Update this path
    test_output_dir = "/path/to/test/output"     # Update this path
    
    if not os.path.exists(test_input_dir):
        logger.warning(f"Test input directory {test_input_dir} does not exist. Skipping single process test.")
        return False
    
    try:
        cmd = [
            "python", "src/ndpi_tile_cropper_parallel_cli.py",
            "-d", test_input_dir,
            "-o", test_output_dir,
            "-n", "1",  # Single process
            "-s", "1024",
            "-l", "0",
            "-r", "2"   # 2 retry attempts
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            logger.info("Single process test PASSED")
            return True
        else:
            logger.error(f"Single process test FAILED: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Single process test TIMEOUT")
        return False
    except Exception as e:
        logger.error(f"Single process test ERROR: {e}")
        return False

def test_parallel_processes():
    """Test parallel process execution with reduced concurrency."""
    logger.info("Testing parallel process execution...")
    
    # You'll need to modify these paths for your test environment
    test_input_dir = "/path/to/test/ndpi/files"  # Update this path
    test_output_dir = "/path/to/test/output"     # Update this path
    
    if not os.path.exists(test_input_dir):
        logger.warning(f"Test input directory {test_input_dir} does not exist. Skipping parallel process test.")
        return False
    
    try:
        cmd = [
            "python", "src/ndpi_tile_cropper_parallel_cli.py",
            "-d", test_input_dir,
            "-o", test_output_dir,
            "-n", "2",  # Reduced to 2 processes
            "-s", "1024",
            "-l", "0",
            "-r", "3"   # 3 retry attempts
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            logger.info("Parallel process test PASSED")
            return True
        else:
            logger.error(f"Parallel process test FAILED: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Parallel process test TIMEOUT")
        return False
    except Exception as e:
        logger.error(f"Parallel process test ERROR: {e}")
        return False

def check_jvm_conflicts_in_logs(log_file):
    """Check if JVM conflicts are present in log files."""
    if not os.path.exists(log_file):
        logger.warning(f"Log file {log_file} does not exist")
        return False
    
    try:
        with open(log_file, 'r') as f:
            content = f.read()
            
        jvm_conflicts = [
            "TJDecompressor",
            "javabridge",
            "JVM conflict",
            "JavaException"
        ]
        
        conflicts_found = []
        for conflict in jvm_conflicts:
            if conflict.lower() in content.lower():
                conflicts_found.append(conflict)
        
        if conflicts_found:
            logger.warning(f"JVM conflicts found in logs: {conflicts_found}")
            return True
        else:
            logger.info("No JVM conflicts found in logs")
            return False
            
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return False

def main():
    """Main test function."""
    logger.info("Starting JVM conflict fix tests...")
    
    # Check if we're in the right directory
    if not os.path.exists("src/ndpi_tile_cropper_parallel_cli.py"):
        logger.error("Please run this script from the project root directory")
        sys.exit(1)
    
    # Test 1: Single process
    single_success = test_single_process()
    
    # Test 2: Parallel processes
    parallel_success = test_parallel_processes()
    
    # Summary
    logger.info("=" * 50)
    logger.info("TEST SUMMARY:")
    logger.info(f"Single process test: {'PASSED' if single_success else 'FAILED'}")
    logger.info(f"Parallel process test: {'PASSED' if parallel_success else 'FAILED'}")
    
    if single_success and parallel_success:
        logger.info("All tests PASSED! JVM conflict fixes appear to be working.")
        return 0
    else:
        logger.error("Some tests FAILED. Please check the logs for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 