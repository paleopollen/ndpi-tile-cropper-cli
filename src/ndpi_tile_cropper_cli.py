import argparse
import logging
import bioformats
import bioformats.formatreader as format_reader
import javabridge
import os
import numpy as np

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
            description='Crop tiles from an NDPISlide.')
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
            '--tile_overlap', '-l',
            type=int,
            default=0,
            help='Overlap of the tiles [not implemented yet].')
        parser.add_argument(
            '--tile_format',
            default='png',
            choices=['png'],
            help='Format of the tiles. [not implemented yet]')
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Display more details.')

        return parser


class NDPIFileCropper:
    """Crop tiles from an NDPISlide."""

    def __init__(self, input_file, output_dir=None, tile_size=1024, tile_overlap=0, tile_format='png'):
        """Initialize an NDPIFileCropper instance."""
        self.input_file = input_file
        if output_dir is None:
            self.output_dir = os.path.dirname(self.input_file)
        else:
            self.output_dir = output_dir
        self.tile_size = tile_size
        self.tile_overlap = tile_overlap
        self.tile_format = tile_format
        self.metadata = dict()

    def read_metadata(self):
        """Read an NDPISlide."""
        logger.info("Read an NDPISlide.")
        ome_xml = bioformats.get_omexml_metadata(self.input_file)
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
        logger.debug("Read a tile from an NDPISlide.")
        img_path = self.input_file

        ImageReader = format_reader.make_image_reader_class()
        reader = ImageReader()
        reader.setId(img_path)
        img = reader.openBytesXYWH(z, x, y, width, height)
        img.shape = (height, width, 3)
        return img

    def crop_tiles(self):
        """Crop tiles from an NDPISlide."""
        logger.info("Crop tiles from an NDPISlide.")
        img_name = os.path.basename(self.input_file).split(' ')[0].split('.')[0]
        # core_name = self.input_file.split('/')[-2].split('_')[0]
        crops_dir = os.path.join(self.output_dir, img_name)
        if not os.path.exists(crops_dir):
            os.makedirs(crops_dir)

        width = self.tile_size
        height = self.tile_size

        # Find total number of image stacks
        start_x_list = np.arange(0, self.metadata['width'] - width, width).tolist()
        start_y_list = np.arange(0, self.metadata['height'] - height, height).tolist()
        start_xy_list = []

        for i in range(len(start_x_list)):
            for j in range(len(start_y_list)):
                x = start_x_list[i]
                y = start_y_list[j]
                xy = (x, y)
                start_xy_list.append(xy)

        logger.info("Number of tiles: " + str(len(start_xy_list)))

        for i in range(len(start_xy_list)):
            start_x = start_xy_list[i][0]
            start_y = start_xy_list[i][1]
            tile_dir = os.path.join(crops_dir, str(start_x) + 'x_' + str(start_y) + 'y')
            if not os.path.exists(tile_dir):
                os.makedirs(tile_dir)
            for j in range(self.metadata['z_plane']):
                img = self.__read_tile(x=start_x, y=start_y, z=j, width=width, height=height)
                im = Image.fromarray(img)
                im.save(os.path.join(tile_dir, str(j) + 'z.png'))
            logger.info("Tile " + str(i) + " complete.")

    def _get_tile_size(self):
        """Get the tile size."""
        return self.tile_size

    def _get_tile_overlap(self):
        """Get the tile overlap."""
        return self.tile_overlap

    def _get_tile_format(self):
        """Get the tile format."""
        return self.tile_format


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)-7s : %(name)s - %(message)s', level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Starting NDPITileCropper CLI")

    javabridge.start_vm(class_path=bioformats.JARS)

    try:
        logback.basic_config()

        cli = NDPITileCropperCLI()
        cli.parse_args()
        cli.print_args()

        ndpi_file_cropper = NDPIFileCropper(cli.args.input_file, cli.args.output_dir, cli.args.tile_size,
                                            cli.args.tile_overlap, cli.args.tile_format)
        ndpi_file_cropper.read_metadata()
        ndpi_file_cropper.crop_tiles()

        javabridge.kill_vm()
        logger.info("Stopping NDPITileCropper CLI")
    except Exception as e:
        logger.info("Stopping NDPITileCropper CLI")
        logger.error(e, exc_info=True)
    finally:
        javabridge.kill_vm()
        logger.info("Stopping NDPITileCropper CLI")
