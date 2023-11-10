#!/usr/bin/env python
# coding: utf-8

import multiprocessing
import os

import bioformats
import bioformats.formatreader as format_reader
import javabridge
import numpy as np
from PIL import Image

javabridge.start_vm(class_path=bioformats.JARS, max_heap_size="4G", run_headless=True)


def img_read(image_filepath,  x=0, y=0, z=0, width=1000, height=1000):
    reader = image_reader()
    reader.setId(image_filepath)
    image = reader.openBytesXYWH(z, x, y, width, height)
    image.shape = (height, width, 3)

    return image


# ndpi image path
img_path = 'PAL1999/C3/PAL1999_C3_sample22_slide1 - 2022-10-11 21.57.44.ndpi'
ome_xml = bioformats.get_omexml_metadata(img_path)
b = bioformats.OMEXML(xml=ome_xml)

metadata = {}
calibration = b.image().Pixels.PhysicalSizeX
calibration_unit = b.image().Pixels.PhysicalSizeXUnit
width = b.image().Pixels.SizeX
height = b.image().Pixels.SizeY
zPlane = b.image().Pixels.SizeZ

metadata.update({'calibration': calibration})
metadata.update({'calibration_unit': calibration_unit})
metadata.update({'width': width})
metadata.update({'height': height})
metadata.update({'zPlane': zPlane})

image_reader = format_reader.make_image_reader_class()
reader = image_reader()
reader.setId(img_path)
image = reader.openBytesXYWH(zPlane, 0, 0, width, height)

img_name = os.path.basename(img_path).split(' ')[0]
core_name = img_path.split('/')[-2].split('_')[0]
crops_dir = os.path.join('Output/', core_name, core_name + '_tiles', img_name + '_5')
if not os.path.exists(crops_dir):
    os.makedirs(crops_dir)

width = 1392
height = 1040

# Find total number of image stacks
start_x_list = np.arange(0, metadata['width'] - width, width).tolist()
start_y_list = np.arange(0, metadata['height'] - height, height).tolist()
start_xy_list = []

for i in range(len(start_x_list)):
    for j in range(len(start_y_list)):
        x = start_x_list[i]
        y = start_y_list[j]
        xy = (x, y)
        start_xy_list.append(xy)


def crop_image(i, start_xy_list, zPlane, crops_dir, img_path, image, width, height):
    start_x = start_xy_list[i][0]
    start_y = start_xy_list[i][1]
    tile_dir = os.path.join(crops_dir, str(start_x) + 'x_' + str(start_y) + 'y')
    if not os.path.exists(tile_dir):
        os.makedirs(tile_dir)
    # print(img_path)
    for j in range(zPlane):
        # img = img_read(img_path, x=start_x, y=start_y, z=j, width=width, height=height)
        image.shape = (height, width, 3)
        im = Image.fromarray(image)
        im.save(os.path.join(tile_dir, str(j) + 'z.png'))
    return i


# index_list = range(len(start_xy_list))
index_list = [0, 1, 2, 3, 4, 5, 6, 7]


with multiprocessing.Pool(processes=4) as pool:
    results = [pool.apply(crop_image, args=(i, start_xy_list, zPlane, crops_dir, img_path, image, width, height)) for i in
               index_list]

# for i in range(len(start_xy_list)):
#     crop_image(i, start_xy_list, zPlane, crops_dir, img_path, width, height)

javabridge.kill_vm()
