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
from tqdm import tqdm


class NDPITileCropperParallelCLI(object):
    """Parallel Command line interface for NDPI Tile Cropper. This works on a directory of NDPI files
    (not recursively)."""

    def __init__(self):
        """Initialize an NDPITileCropperParallelCLI instance."""
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
            description='Crop and generate tile images from an NDPI format image file using parallel processing.')
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
            default=8,
            help='Number of processes to use for parallel processing.')
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

        return parser

    def _get_input_files(self):
        """Get the input files."""
        input_files = []
        for file in os.listdir(self.args.input_dir):
            if file.endswith(".ndpi"):
                input_files.append(os.path.join(self.args.input_dir, file))
        return input_files

    def __process_file(self, input_file):
        """Process a file with optimized JVM settings."""
        logger.info("Started processing file: {}".format(input_file))
        if self.args.output_dir:
            output_dir = self.args.output_dir
        else:
            output_dir = os.path.splitext(input_file)[0] + "_tiles"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Set JVM memory options for better performance
        env = os.environ.copy()
        env['JAVA_OPTS'] = f"-Xmx4g -Xms2g -XX:+UseG1GC"
        
        command = ["python", "ndpi_tile_cropper_cli.py", "-i", input_file, "-o", output_dir, "-s", str(self.args.tile_size),
                   "-l", str(self.args.tile_overlap), "-g", str(self.args.log_level), "-n", str(self.args.num_processes)]

        if self.args.overwrite:
            command.append("-w")
        if self.args.zip:
            command.append("-z")
        if self.args.verbose:
            command.append("-v")

        result = subprocess.run(command, env=env)
        logger.info(result)
        logger.info("Finished processing file: {}".format(input_file))

    def process_files_in_parallel(self):
        """Process the files in parallel with progress tracking."""
        logger.info("Started processing files in parallel")
        input_files = self._get_input_files()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.args.num_processes) as executor:
            # Submit all tasks and collect futures
            futures = [executor.submit(self.__process_file, input_file) for input_file in input_files]
            
            # Wait for all tasks to complete with progress bar
            with tqdm(total=len(futures), desc="Processing files", unit="file") as pbar:
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()  # This will raise any exceptions that occurred
                    except Exception as e:
                        logger.error(f"Error processing file: {e}")
                    pbar.update(1)
        
        logger.info("Finished processing files in parallel")


if __name__ == '__main__':
    # Create an instance of the CLI and parse the arguments
    cli = NDPITileCropperParallelCLI()
    cli.parse_args()
    cli.print_args()

    # Set up logging
    logging.basicConfig(format='%(asctime)s %(levelname)-7s : %(name)s - %(message)s', level=cli.args.log_level)
    logger = logging.getLogger("ndpi_tile_cropper_parallel_cli.py")

    # Process the files in parallel
    cli.process_files_in_parallel()
