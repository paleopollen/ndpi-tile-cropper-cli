import slideio
slide = slideio.open_slide("/Users/sandeep/Repositories/PALYIM/ndpi-tile-cropper-cli/data/PAL1999/C3/PAL1999_C3_sample22_slide1 - 2022-10-11 21.57.44.ndpi", "NDPI")
print("Slide opened")
scene = slide.get_scene(0)
print("Scene extracted")
img = scene.read_block()
print("Image read")
print(img.size)