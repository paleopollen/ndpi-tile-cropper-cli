import argparse
import logging
import bioformats
import bioformats.formatreader as format_reader
# import javabridge
import os
import glob
import slideio
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
            '--overwrite', '-w',
            action='store_true',
            help='Overwrite existing tiles.')
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

    def __init__(self, input_file, output_dir=None, tile_size=1024, tile_overlap=0, tile_format='png', overwrite=False):
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
        self.metadata = dict()

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

    def read_image(self):
        """Read an NDPISlide."""
        logger.info(self.input_filename + ": Read NDPISlide")
        slide = slideio.open_slide(self.input_file_path, "AUTO")
        scene = slide.get_scene(0)
        img = scene.read_block()
        print(img.num_aux_images)
        print(img.num_scenes)
        print(img.file_path)
        print(img.raw_metadata)
        return img
    def __read_tile(self, x, y, z, width, height):
        """Read a tile from an NDPISlide."""
        logger.debug(self.input_filename + ": Read a tile from NDPISlide: " + str(x) + "x_" + str(y) + "y_" + str(z) + "z")
        img_path = self.input_file_path

        ImageReader = format_reader.make_image_reader_class()
        reader = ImageReader()
        reader.setId(img_path)
        img = reader.openBytesXYWH(z, x, y, width, height)
        img.shape = (height, width, 3)
        return img

    @staticmethod
    def __count_files(directory, file_extension):
        files = glob.glob(os.path.join(directory, "*." + file_extension))
        return len(files)

    def crop_tiles(self):
        """Crop tiles from an NDPISlide."""
        logger.info(self.input_filename + ": Crop tiles from NDPISlide")
        img_name = os.path.basename(self.input_file_path).split(' ')[0].split('.')[0]
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

        logger.info(self.input_filename + ": Number of tiles: " + str(len(start_xy_list)))

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
                    im = Image.fromarray(img)
                    im.save(os.path.join(tile_dir, str(j) + 'z.png'))
            else:
                logger.info(self.input_filename + ": Tile " + str(i) + " already exists. Skipping...")
            logger.info(self.input_filename + ": Tile " + str(i) + " complete.")

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
    logger = logging.getLogger("ndpi_tile_cropper_cli.py")
    logger.info("Starting NDPITileCropper CLI")

    try:
        # logback.basic_config()

        cli = NDPITileCropperCLI()
        cli.parse_args()
        cli.print_args()

        ndpi_file_cropper = NDPIFileCropper(cli.args.input_file, cli.args.output_dir, cli.args.tile_size,
                                            cli.args.tile_overlap, cli.args.tile_format, cli.args.overwrite)
        # ndpi_file_cropper.read_metadata()
        ndpi_file_cropper.read_image()

        # javabridge.start_vm(class_path=bioformats.JARS)
        # ndpi_file_cropper.crop_tiles()
        #
        # javabridge.kill_vm()
        logger.info("Stopping NDPITileCropper CLI")
    except Exception as e:
        logger.info("Stopping NDPITileCropper CLI")
        logger.error(e, exc_info=True)
    finally:
        # javabridge.kill_vm()
        logger.info("Stopping NDPITileCropper CLI")
