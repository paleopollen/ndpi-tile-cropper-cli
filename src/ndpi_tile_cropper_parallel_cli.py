import argparse
import logging
import subprocess
import concurrent.futures
import os


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
            description='Crop tiles from an NDPISlide using parallel processing.')
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
            '--num_processes', '-n',
            type=int,
            default=8,
            help='Number of processes to use for parallel processing.')
        parser.add_argument(
            '--overwrite', '-w',
            action='store_true',
            help='Overwrite existing tiles.')
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
        """Process a file."""
        logger.info("Started processing file: {}".format(input_file))
        if self.args.output_dir:
            output_dir = self.args.output_dir
        else:
            output_dir = os.path.splitext(input_file)[0] + "_tiles"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        command = ["python", "ndpi_tile_cropper_cli.py", "-i", input_file, "-o", output_dir]

        if self.args.overwrite:
            command.append("-w")
        if self.args.verbose:
            command.append("-v")

        result = subprocess.run(command)
        logger.info(result)
        logger.info("Finished processing file: {}".format(input_file))

    def process_files_in_parallel(self):
        """Process the files in parallel."""
        logger.info("Started processing files in parallel")
        input_files = self._get_input_files()
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.args.num_processes) as executor:
            for input_file in input_files:
                executor.submit(self.__process_file, input_file)
        logger.info("Finished processing files in parallel")


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)-7s : %(name)s - %(message)s', level=logging.INFO)
    logger = logging.getLogger("ndpi_tile_cropper_parallel_cli.py")
    cli = NDPITileCropperParallelCLI()
    cli.parse_args()
    cli.print_args()
    cli.process_files_in_parallel()
