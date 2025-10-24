#  Copyright 2024 The Board of Trustees of the University of Illinois. All Rights Reserved.
#
#  Licensed under the terms of Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  The License is included in the distribution as LICENSE file.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import argparse
import concurrent.futures
import logging
import os
import subprocess
import time
import random


class NDPITileCropperParallelCLISimple(object):
    """Simple Parallel Command line interface for NDPI Tile Cropper using ThreadPoolExecutor.
    This avoids pickling issues while still providing JVM conflict handling."""

    def __init__(self):
        """Initialize an NDPITileCropperParallelCLISimple instance."""
        self.parser = self._create_parser()
        self.args = None

    def parse_args(self):
        """Parse the command line arguments."""
        self.args = self.parser.parse_args()

    def print_args(self):
        if self.args.verbose:
            """Print the command line arguments."""
            print("\nArguments\tValues")
            print("======================")
            for key, value in self.args.__dict__.items():
                print(key, ":", value)
            print("======================\n")

    @staticmethod
    def _create_parser():
        """Create a parser for the command line arguments."""
        parser = argparse.ArgumentParser(
            description='Crop and generate tile images from an NDPI format image file using simple parallel processing.')
        parser.add_argument(
            '--input-dir', '-d',
            nargs='?', default=None, required=True,
            help='Path to the input NDPISlide directory. E.g., data/NDPI')
        parser.add_argument(
            '--output-dir', '-o',
            nargs='?', default=None, required=False,
            help='Path to the output directory. E.g., data/NDPI/NDPI_1_tiles. If no output directory path is provided, '
                 'the program will create a directory using the input file\'s name and save the tiles in that '
                 'directory.')
        parser.add_argument(
            '--tile_size', '-s',
            type=int,
            default=1024,
            required=False,
            help='Size of the tiles to crop. Only square tiles are supported at present.')
        parser.add_argument(
            '--tile_overlap', '-l',
            type=int,
            default=0,
            required=False,
            help='Overlap of the tiles in pixels.')
        parser.add_argument(
            '--num_processes', '-n',
            type=int,
            default=2,
            help='Number of threads to use for parallel processing. Reduced default to avoid JVM conflicts.')
        parser.add_argument(
            '--overwrite', '-w',
            action='store_true',
            help='Overwrite existing tiles.')
        parser.add_argument(
            '--zip', '-z',
            action='store_true',
            help='Zip the tiles output directory and remove the tiles directory. Unzip the tiles directory zip file, if it exists, before starting with the tiles creation.')
        parser.add_argument(
            '--log-level', '-g',
            type=str,
            nargs='?',
            default='INFO',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            help='Set the logging level.')
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Display more details.')
        parser.add_argument(
            '--retry-attempts', '-r',
            type=int,
            default=3,
            help='Number of retry attempts for failed processing due to JVM conflicts.')

        return parser

    def _get_input_files(self):
        """Get the input files."""
        input_files = []
        for file in os.listdir(self.args.input_dir):
            if file.endswith(".ndpi"):
                input_files.append(os.path.join(self.args.input_dir, file))
        return input_files

    def __process_file(self, input_file):
        """Process a file with retry logic for JVM conflicts."""
        logger = logging.getLogger("ndpi_tile_cropper_parallel_cli_simple.py")
        logger.info("Started processing file: {}".format(input_file))
        
        if self.args.output_dir:
            output_dir = self.args.output_dir
        else:
            output_dir = os.path.splitext(input_file)[0] + "_tiles"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        command = ["python", "ndpi_tile_cropper_cli.py", "-i", input_file, "-o", output_dir, "-s", str(self.args.tile_size),
                   "-l", str(self.args.tile_overlap), "-g", str(self.args.log_level)]

        if self.args.overwrite:
            command.append("-w")
        if self.args.zip:
            command.append("-z")
        if self.args.verbose:
            command.append("-v")

        # Retry logic for JVM conflicts
        for attempt in range(self.args.retry_attempts):
            try:
                # Add a small random delay to reduce JVM startup conflicts
                if attempt > 0:
                    delay = random.uniform(2.0, 8.0)
                    logger.info(f"Retry attempt {attempt + 1} for {input_file}, waiting {delay:.2f}s...")
                    time.sleep(delay)
                
                result = subprocess.run(command, capture_output=True, text=True, timeout=3600)  # 1 hour timeout
                
                if result.returncode == 0:
                    logger.info("Successfully finished processing file: {}".format(input_file))
                    return True
                else:
                    logger.error(f"Process failed for {input_file} (attempt {attempt + 1}): {result.stderr}")
                    if "TJDecompressor" in result.stderr or "javabridge" in result.stderr.lower():
                        logger.warning(f"JVM conflict detected for {input_file}, will retry...")
                        continue
                    else:
                        logger.error(f"Non-JVM error for {input_file}, not retrying")
                        return False
                        
            except subprocess.TimeoutExpired:
                logger.error(f"Process timeout for {input_file} (attempt {attempt + 1})")
                continue
            except Exception as e:
                logger.error(f"Unexpected error processing {input_file} (attempt {attempt + 1}): {str(e)}")
                continue
        
        logger.error(f"Failed to process {input_file} after {self.args.retry_attempts} attempts")
        return False

    def process_files_in_parallel(self):
        """Process the files in parallel using ThreadPoolExecutor."""
        logger = logging.getLogger("ndpi_tile_cropper_parallel_cli_simple.py")
        logger.info("Started processing files in parallel (simple mode)")
        input_files = self._get_input_files()
        
        if not input_files:
            logger.warning("No .ndpi files found in the input directory")
            return
            
        logger.info(f"Found {len(input_files)} .ndpi files to process")
        
        # Use ThreadPoolExecutor to avoid pickling issues
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.args.num_processes) as executor:
            # Submit all tasks
            future_to_file = {executor.submit(self.__process_file, input_file): input_file 
                            for input_file in input_files}
            
            # Process completed tasks
            successful = 0
            failed = 0
            
            for future in concurrent.futures.as_completed(future_to_file):
                input_file = future_to_file[future]
                try:
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as exc:
                    logger.error(f"File {input_file} generated an exception: {exc}")
                    failed += 1
        
        logger.info(f"Finished processing files in parallel. Successful: {successful}, Failed: {failed}")


if __name__ == '__main__':
    # Create an instance of the CLI and parse the arguments
    cli = NDPITileCropperParallelCLISimple()
    cli.parse_args()
    cli.print_args()

    # Set up logging
    logging.basicConfig(format='%(asctime)s %(levelname)-7s : %(name)s - %(message)s', level=cli.args.log_level)
    logger = logging.getLogger("ndpi_tile_cropper_parallel_cli_simple.py")

    # Process the files in parallel
    cli.process_files_in_parallel() 