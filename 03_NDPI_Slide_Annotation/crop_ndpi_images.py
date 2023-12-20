import os
import numpy as np
from openslide import OpenSlide
from PIL import Image
# import bioformats.formatreader as format_reader


class ImageReader:
    def __init__(self, img_filepath):
        self.image_filepath = img_filepath
        self.slide = None
        self.crops_dir = None
        self.properties = None
        self.metadata = dict()

    def read(self):
        self.slide = OpenSlide(self.image_filepath)
        # print(self.slide.dimensions)
        # print(self.slide.properties)

        self.metadata["calibration"] = self.slide.properties.get("openslide.mpp-x")
        self.metadata["calibration_unit"] = "µm"
        self.metadata["width"] = self.slide.dimensions[0]
        self.metadata["height"] = self.slide.dimensions[0]
        self.metadata["zPlane"] = self.slide.level_count
        self.slide.properties.get('openslide.level-count', 1)
        print(self.metadata)

    def process(self):

        # Create output directory
        img_name = os.path.basename(img_path).split(' ')[0]
        core_name = img_path.split('/')[-2].split('_')[0]
        self.crops_dir = os.path.join('Output/', core_name, core_name + '_tiles', img_name)
        if not os.path.exists(self.crops_dir):
            os.makedirs(self.crops_dir)
        print(img_name)
        print(core_name)
        print(self.crops_dir)

        width = 1024
        height = 1024

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

        for i in range(len(start_xy_list)):
            start_x = start_xy_list[i][0]
            start_y = start_xy_list[i][1]
            tile_dir = os.path.join(self.crops_dir, str(start_x) + 'x_' + str(start_y) + 'y')
            if not os.path.exists(tile_dir):
                os.makedirs(tile_dir)
            for j in range(self.metadata["zPlane"]):
                img = self.slide.read_region((start_x, start_y), j, (width, height))
                # img = img_read(img_path, x=start_x, y=start_y, z=j, width=width, height=height)
                img = img.convert('RGB')
                # im = Image.fromarray(img)
                img.save(os.path.join(tile_dir, str(j) + 'z.png'))
            print(i)

    # def _img_read(self, image_filepath, x=0, y=0, z=0, width=1000, height=1000):
    #     image_reader = format_reader.make_image_reader_class()
    #     reader = image_reader()
    #     reader.setId(image_filepath)
    #     image = reader.openBytesXYWH(z, x, y, width, height)
    #     image.shape = (height, width, 3)
    #
    #     return image

    # def crop_image(self, i, start_xy_list, zPlane, crops_dir, img_path, width, height):
    #     # print(i)
    #     start_x = start_xy_list[i][0]
    #     start_y = start_xy_list[i][1]
    #     tile_dir = os.path.join(crops_dir, str(start_x) + 'x_' + str(start_y) + 'y')
    #     if not os.path.exists(tile_dir):
    #         os.makedirs(tile_dir)
    #     # print(img_path)
    #     for j in range(zPlane):
    #         img = _img_read(img_path, x=start_x, y=start_y, z=j, width=width, height=height)
    #         im = Image.fromarray(img)
    #         im.save(os.path.join(tile_dir, str(j) + 'z.png'))
    #     return i


if __name__ == '__main__':
    img_path = 'PAL1999/C3/PAL1999_C3_sample22_slide1 - 2022-10-11 21.57.44.ndpi'
    reader = ImageReader(img_path)
    reader.read()
    reader.process()
