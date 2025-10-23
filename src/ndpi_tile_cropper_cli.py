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
import glob
import json
import logging
import os
import shutil
import signal
import multiprocessing as mp
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

import bioformats
import bioformats.formatreader as format_reader
import javabridge
import numpy as np

from zipfile import ZipFile
from PIL import Image
from bioformats import logback


class NDPITileCropperCLI(object):
    """Command line interface for NDPITileCropper."""

    def __init__(self):
        """Initialize an NDPITileCropperCLI instance."""
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
            description='Crop and generate tile images from an NDPI format image file')
        parser.add_argument(
            '--input-file', '-i',
            nargs='?', default=None, required=True,
            help='Path to the input NDPISlide file. E.g., data/NDPI/NDPI_1.ndpi')
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
            help='Size of the tiles to crop. Only square tiles are supported at present.')
        parser.add_argument(
            '--overwrite', '-w',
            action='store_true',
            help='Overwrite existing tiles.')
        parser.add_argument(
            '--tile_overlap', '-l',
            type=int,
            default=0,
            help='Overlap of the tiles in pixels.')
        parser.add_argument(
            '--tile_format',
            default='png',
            choices=['png'],
            help='Format of the tiles. [not implemented yet]')
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
            '--num_processes', '-n',
            type=int,
            default=1,
            help='Number of processes to use for parallel tile processing.')

        return parser


class NDPIFileCropper:
    """Crop tiles from an NDPISlide."""

    def __init__(self, input_file, output_dir=None, tile_size=1024, tile_overlap=0, tile_format='png', overwrite=False,
                 zip_flag=False):
        """Initialize an NDPIFileCropper instance."""
        self.input_file_path = input_file
        self.input_filename = os.path.basename(self.input_file_path)
        if output_dir is None:
            self.output_dir = os.path.dirname(self.input_file_path)
        else:
            self.output_dir = output_dir
        self.tile_size = tile_size
        self.tile_overlap = tile_overlap
        self.tile_format = tile_format
        self.overwrite_flag = overwrite
        self.zip_flag = zip_flag
        self.metadata = dict()

        self.total_tile_count = 0
        self.processed_tile_count = 0

        # Handle SIGINT and SIGTERM
        signal.signal(signal.SIGINT, self.exit_program)
        signal.signal(signal.SIGTERM, self.exit_program)

    def read_metadata(self):
        """Read an NDPISlide."""
        logger.info(self.input_filename + ": Read NDPISlide metadata")
        ome_xml = bioformats.get_omexml_metadata(self.input_file_path)
        b = bioformats.OMEXML(xml=ome_xml)

        calibration = b.image().Pixels.PhysicalSizeX
        calibration_unit = b.image().Pixels.PhysicalSizeXUnit
        width = b.image().Pixels.SizeX
        height = b.image().Pixels.SizeY
        z_plane = b.image().Pixels.SizeZ

        self.metadata['calibration'] = calibration
        self.metadata['calibration_unit'] = calibration_unit
        self.metadata['width'] = width
        self.metadata['height'] = height
        self.metadata['z_plane'] = z_plane

    def __read_tile(self, x, y, z, width, height):
        """Read a tile from an NDPISlide."""
        logger.debug(self.input_filename + ": Read a tile from NDPISlide: " + str(x) + "x_" + str(y) + "y_" + str(z) + "z")
        img_path = self.input_file_path

        ImageReader = format_reader.make_image_reader_class()
        reader = ImageReader()
        img = None
        try:
            reader.setId(img_path)
            img = reader.openBytesXYWH(z, x, y, width, height)
            img.shape = (height, width, 3)
        except Exception as ex:
            logger.error(self.input_filename + ": Error reading tile: " + str(x) + "x_" + str(y) + "y_" + str(z) + "z")
            logger.error(ex, exc_info=True)
        finally:
            reader.close()
            return img

    @staticmethod
    def __count_files(directory, file_extension):
        files = glob.glob(os.path.join(directory, "*." + file_extension))
        return len(files)

    def crop_tiles(self, num_processes=None):
        """Crop tiles from an NDPISlide with optional parallel processing."""
        if num_processes is not None:
            return self.crop_tiles_parallel(num_processes)
        else:
            return self.crop_tiles_sequential()
    
    def crop_tiles_sequential(self):
        """Crop tiles from an NDPISlide (original sequential method)."""
        logger.info(self.input_filename + ": Crop tiles from NDPISlide (sequential)")
        img_name = os.path.basename(self.input_file_path).split(' ')[0].rsplit('.', maxsplit=1)[0]
        crops_dir = str(os.path.join(self.output_dir, img_name))
        if not os.path.exists(crops_dir):
            os.makedirs(crops_dir)

        width = self._get_tile_size()
        height = self._get_tile_size()
        overlap = self._get_tile_overlap()

        # Find total number of image stacks
        start_x_list = np.arange(0, self.metadata['width'] - width, width - overlap).tolist()
        start_y_list = np.arange(0, self.metadata['height'] - height, height - overlap).tolist()
        start_xy_list = []

        for i in range(len(start_x_list)):
            for j in range(len(start_y_list)):
                x = start_x_list[i]
                y = start_y_list[j]
                xy = (x, y)
                start_xy_list.append(xy)

        logger.info(self.input_filename + ": Number of tiles: " + str(len(start_xy_list)))
        self.total_tile_count = len(start_xy_list)

        crops_dir_metadata_dict = dict()
        crops_dir_metadata_dict['tile_size'] = self.tile_size
        crops_dir_metadata_dict['tile_overlap'] = self.tile_overlap
        crops_dir_metadata_dict['ome_metadata'] = self.metadata
        crops_dir_metadata_dict['total_tile_count'] = self.total_tile_count
        crops_dir_metadata_dict['processed_tile_count'] = 0
        crops_dir_metadata_dict['percent_complete'] = 0.0

        crops_dir_metadata_file_path = os.path.join(crops_dir, 'metadata.json')

        # Write metadata to the crops directory if it does not exist
        if not os.path.exists(crops_dir_metadata_file_path):
            with open(crops_dir_metadata_file_path, 'w') as f:
                json.dump(crops_dir_metadata_dict, f, indent=4)

        for i in range(len(start_xy_list)):
            start_x = start_xy_list[i][0]
            start_y = start_xy_list[i][1]
            tile_dir = os.path.join(str(crops_dir), str(start_x) + 'x_' + str(start_y) + 'y')
            if not os.path.exists(tile_dir):
                os.makedirs(tile_dir)

            z_plane_image_count = self.__count_files(tile_dir, self.tile_format)
            # Proceed only if the number of z-plane images is less than the number of z-planes in the image or if the
            # overwrite flag is set
            if z_plane_image_count < self.metadata['z_plane'] or self.overwrite_flag:
                for j in range(self.metadata['z_plane']):
                    img = self.__read_tile(x=start_x, y=start_y, z=j, width=width, height=height)
                    if img is not None:
                        im = Image.fromarray(img)
                        im.save(os.path.join(tile_dir, str(j) + 'z.png'))
            else:
                logger.info(self.input_filename + ": Tile " + str(i) + " already exists. Skipping...")
            self.processed_tile_count += 1
            logger.info(self.input_filename + ": Tile " + str(i) + " complete.")

    def crop_tiles_parallel(self, num_processes):
        """Crop tiles from an NDPISlide using optimized sequential processing."""
        logger.info(self.input_filename + f": Crop tiles from NDPISlide (optimized, {num_processes} processes)")
        img_name = os.path.basename(self.input_file_path).split(' ')[0].rsplit('.', maxsplit=1)[0]
        crops_dir = str(os.path.join(self.output_dir, img_name))
        if not os.path.exists(crops_dir):
            os.makedirs(crops_dir)

        width = self._get_tile_size()
        height = self._get_tile_size()
        overlap = self._get_tile_overlap()

        # Find total number of image stacks
        start_x_list = np.arange(0, self.metadata['width'] - width, width - overlap).tolist()
        start_y_list = np.arange(0, self.metadata['height'] - height, height - overlap).tolist()
        start_xy_list = []

        for i in range(len(start_x_list)):
            for j in range(len(start_y_list)):
                x = start_x_list[i]
                y = start_y_list[j]
                xy = (x, y)
                start_xy_list.append(xy)

        logger.info(self.input_filename + ": Number of tiles: " + str(len(start_xy_list)))
        self.total_tile_count = len(start_xy_list)

        # Write metadata
        crops_dir_metadata_dict = dict()
        crops_dir_metadata_dict['tile_size'] = self.tile_size
        crops_dir_metadata_dict['tile_overlap'] = self.tile_overlap
        crops_dir_metadata_dict['ome_metadata'] = self.metadata
        crops_dir_metadata_dict['total_tile_count'] = self.total_tile_count
        crops_dir_metadata_dict['processed_tile_count'] = 0
        crops_dir_metadata_dict['percent_complete'] = 0.0

        crops_dir_metadata_file_path = os.path.join(crops_dir, 'metadata.json')
        if not os.path.exists(crops_dir_metadata_file_path):
            with open(crops_dir_metadata_file_path, 'w') as f:
                json.dump(crops_dir_metadata_dict, f, indent=4)

        # Use optimized sequential processing with better I/O patterns
        logger.info(self.input_filename + f": Starting optimized tile processing")
        
        # Pre-allocate reader for better performance
        ImageReader = format_reader.make_image_reader_class()
        reader = ImageReader()
        reader.setId(self.input_file_path)
        
        try:
            # Process tiles with progress bar
            with tqdm(total=len(start_xy_list), desc=f"Processing tiles for {self.input_filename}", unit="tile") as pbar:
                for i, (start_x, start_y) in enumerate(start_xy_list):
                    try:
                        self._process_single_tile_optimized(i, start_x, start_y, width, height, crops_dir, reader)
                        self.processed_tile_count += 1
                    except Exception as e:
                        logger.error(f"Error processing tile {i}: {e}")
                    pbar.update(1)
        finally:
            reader.close()
        
        logger.info(self.input_filename + f": Completed processing {self.processed_tile_count} tiles")

    def _process_single_tile_optimized(self, tile_index, start_x, start_y, width, height, crops_dir, reader):
        """Process a single tile with optimized I/O."""
        try:
            tile_dir = os.path.join(str(crops_dir), str(start_x) + 'x_' + str(start_y) + 'y')
            if not os.path.exists(tile_dir):
                os.makedirs(tile_dir)

            z_plane_image_count = self.__count_files(tile_dir, self.tile_format)
            
            if z_plane_image_count < self.metadata['z_plane'] or self.overwrite_flag:
                # Process all z-planes for this tile
                for j in range(self.metadata['z_plane']):
                    try:
                        img = reader.openBytesXYWH(j, start_x, start_y, width, height)
                        img.shape = (height, width, 3)
                        
                        if img is not None:
                            im = Image.fromarray(img)
                            im.save(os.path.join(tile_dir, str(j) + 'z.png'))
                    except Exception as e:
                        logger.error(f"Error processing z-plane {j} for tile {tile_index}: {e}")
            else:
                logger.info(self.input_filename + ": Tile " + str(tile_index) + " already exists. Skipping...")
            
            logger.info(self.input_filename + ": Tile " + str(tile_index) + " complete.")
            return True
            
        except Exception as e:
            logger.error(f"Error processing tile {tile_index}: {e}")
            return False

    def _process_single_tile_threaded(self, tile_index, start_x, start_y, width, height, crops_dir):
        """Process a single tile using threading (shared JVM)."""
        import threading
        
        # Use a lock to ensure thread-safe access to the JVM
        if not hasattr(self, '_jvm_lock'):
            self._jvm_lock = threading.Lock()
        
        try:
            tile_dir = os.path.join(str(crops_dir), str(start_x) + 'x_' + str(start_y) + 'y')
            if not os.path.exists(tile_dir):
                os.makedirs(tile_dir)

            z_plane_image_count = self.__count_files(tile_dir, self.tile_format)
            
            if z_plane_image_count < self.metadata['z_plane'] or self.overwrite_flag:
                # Process all z-planes for this tile
                for j in range(self.metadata['z_plane']):
                    # Use lock to ensure thread-safe JVM access
                    with self._jvm_lock:
                        img = self.__read_tile(x=start_x, y=start_y, z=j, width=width, height=height)
                    
                    if img is not None:
                        im = Image.fromarray(img)
                        im.save(os.path.join(tile_dir, str(j) + 'z.png'))
            else:
                logger.info(self.input_filename + ": Tile " + str(tile_index) + " already exists. Skipping...")
            
            logger.info(self.input_filename + ": Tile " + str(tile_index) + " complete.")
            return True
            
        except Exception as e:
            logger.error(f"Error processing tile {tile_index}: {e}")
            return False

    def write_metadata_before_exiting(self):
        crops_dir = str(os.path.join(self.output_dir, os.path.basename(self.input_file_path).split(' ')[0].rsplit('.', maxsplit=1)[0]))
        crops_dir_metadata_file_path = os.path.join(crops_dir, 'metadata.json')
        if os.path.exists(crops_dir_metadata_file_path):
            with open(crops_dir_metadata_file_path, 'r') as f:
                existing_metadata = json.load(f)
                existing_metadata['processed_tile_count'] = self.processed_tile_count
                # Check if total_tile_count is 0 to avoid division by zero
                if self.total_tile_count == 0:
                    existing_metadata['percent_complete'] = 0.0
                else:
                    # Calculate the percentage of tiles processed
                    existing_metadata['percent_complete'] = round((self.processed_tile_count / self.total_tile_count) * 100, 2)
            with open(crops_dir_metadata_file_path, 'w') as f:
                logger.info(self.input_filename + ": Writing metadata to " + crops_dir_metadata_file_path)
                json.dump(existing_metadata, f, indent=4)
        else:
            logger.error(self.input_filename + ": Metadata file not found. Exiting without updating metadata.")

    def zip_tiles(self):
        """Zip the tiles output directory and remove the directory."""
        img_name = os.path.basename(self.input_file_path).split(' ')[0].rsplit('.', maxsplit=1)[0]
        crops_dir_path = str(os.path.join(self.output_dir, img_name))
        zip_file_path = crops_dir_path + '.zip'
        with ZipFile(zip_file_path, 'w') as zip_file:
            for root, dirs, files in os.walk(crops_dir_path):
                for file in files:
                    zip_file.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), crops_dir_path))
            logger.info(self.input_filename + ": Zipped tiles to " + crops_dir_path + '.zip')
            logger.info(self.input_filename + ": Removing directory " + crops_dir_path)
            shutil.rmtree(crops_dir_path)

    def unzip_tiles(self):
        """Unzip the tiles output directory."""
        img_name = os.path.basename(self.input_file_path).split(' ')[0].rsplit('.', maxsplit=1)[0]
        crops_dir_path = str(os.path.join(self.output_dir, img_name))
        zip_file_path = crops_dir_path + '.zip'

        # If the crops directory already exists, give priority to that and skip unzipping
        if os.path.exists(crops_dir_path):
            logger.info(self.input_filename + ": Directory " + crops_dir_path + " already exists. Skipping unzipping...")
            return

        if os.path.exists(zip_file_path):
            with ZipFile(zip_file_path, 'r') as zip_file:
                for info in zip_file.infolist():
                    # Check if the zip file contents starts with the image name
                    if info.filename.startswith(img_name + '/'):
                        zip_file.extractall(self.output_dir)
                        logger.info(self.input_filename + ": Unzipped tiles to " + crops_dir_path)
                    else:
                        zip_file.extractall(crops_dir_path)
                        logger.info(self.input_filename + ": Unzipped tiles to " + crops_dir_path)
        else:
            logger.info(self.input_filename + ": Zip file not found. Skipping unzipping...")

    def _get_tile_size(self):
        """Get the tile size."""
        return self.tile_size

    def _get_tile_overlap(self):
        """Get the tile overlap."""
        return self.tile_overlap

    def _get_tile_format(self):
        """Get the tile format."""
        return self.tile_format

    def exit_program(self, signum, frame):
        """Exit the program."""
        logger.info("Received signal: " + str(signum))
        self.write_metadata_before_exiting()
        logger.info("Shutting down JVM.")
        javabridge.kill_vm()
        logger.info("Stopping NDPITileCropper CLI...")
        exit(0)


def process_single_tile_parallel(args):
    """Process a single tile in a separate process for parallel execution."""
    import bioformats
    import bioformats.formatreader as format_reader
    import javabridge
    from PIL import Image
    import os
    import glob
    import logging
    import time
    import random
    
    # Set up logging for this process
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-7s : %(name)s - %(message)s')
    logger = logging.getLogger(f"tile_processor_{args['tile_index']}")
    
    try:
        # Add random delay to prevent JVM startup conflicts
        time.sleep(random.uniform(0.1, 0.5))
        
        # Start JVM for this process with better isolation
        javabridge.start_vm(
            class_path=bioformats.JARS, 
            run_headless=True,
            max_heap_size='2g',
            jvm_options=['-Djava.awt.headless=true', '-XX:+UseG1GC']
        )
        
        # Create tile directory
        tile_dir = os.path.join(args['crops_dir'], f"{args['start_x']}x_{args['start_y']}y")
        if not os.path.exists(tile_dir):
            os.makedirs(tile_dir)
        
        # Check if tile already exists
        existing_files = glob.glob(os.path.join(tile_dir, f"*.{args['tile_format']}"))
        if len(existing_files) >= args['z_planes'] and not args['overwrite_flag']:
            logger.info(f"Tile {args['tile_index']} already exists. Skipping...")
            return True
        
        # Process all z-planes for this tile
        for z in range(args['z_planes']):
            try:
                # Read tile from NDPI file
                ImageReader = format_reader.make_image_reader_class()
                reader = ImageReader()
                reader.setId(args['input_file_path'])
                
                img = reader.openBytesXYWH(z, args['start_x'], args['start_y'], args['width'], args['height'])
                img.shape = (args['height'], args['width'], 3)
                
                # Save image
                im = Image.fromarray(img)
                im.save(os.path.join(tile_dir, f"{z}z.png"))
                
                reader.close()
                
            except Exception as e:
                logger.error(f"Error processing z-plane {z} for tile {args['tile_index']}: {e}")
                return False
        
        logger.info(f"Tile {args['tile_index']} completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error processing tile {args['tile_index']}: {e}")
        return False
    finally:
        # Clean up JVM
        try:
            javabridge.kill_vm()
        except:
            pass


if __name__ == '__main__':

    # Start the JVM
    javabridge.start_vm(class_path=bioformats.JARS, run_headless=True)

    # Parse the command line arguments
    cli = NDPITileCropperCLI()
    cli.parse_args()
    cli.print_args()

    # Set the logging level
    logging.basicConfig(format='%(asctime)s %(levelname)-7s : %(name)s - %(message)s', level=cli.args.log_level)
    logger = logging.getLogger("ndpi_tile_cropper_cli.py")
    logger.info("Starting NDPITileCropper CLI")

    # Create an NDPIFileCropper instance
    ndpi_file_cropper = NDPIFileCropper(cli.args.input_file, cli.args.output_dir, cli.args.tile_size,
                                        cli.args.tile_overlap, cli.args.tile_format, cli.args.overwrite)

    try:
        logback.basic_config()

        # Read the metadata of the NDPISlide
        ndpi_file_cropper.read_metadata()

        # Unzip the tiles directory if the zip flag is set and if the zip file exists
        if cli.args.zip:
            ndpi_file_cropper.unzip_tiles()

        # Crop tiles from the NDPISlide
        ndpi_file_cropper.crop_tiles(cli.args.num_processes)

        # Write metadata before exiting
        ndpi_file_cropper.write_metadata_before_exiting()

        # Zip the tiles directory if the zip flag is set
        if cli.args.zip:
            ndpi_file_cropper.zip_tiles()

    except Exception as e:
        logger.info("Exception in NDPITileCropper CLI")
        logger.error(e, exc_info=True)
    finally:
        # Write metadata before exiting
        ndpi_file_cropper.write_metadata_before_exiting()

        # Stop the JVM
        logger.info("Shutting down JVM.")
        javabridge.kill_vm()
        logger.info("Stopping NDPITileCropper CLI")
