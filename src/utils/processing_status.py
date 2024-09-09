import json
import os
import sys


# Visit all the output folders, and read the metadata.json file, print the total number of tiles, and percent complete along with the folder name


def get_tile_count(output_dir):
    metadata_file = os.path.join(output_dir, 'metadata.json')
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        return metadata['total_tile_count']
    else:
        return None


def get_percent_complete(output_dir):
    metadata_file = os.path.join(output_dir, 'metadata.json')
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        return metadata['percent_complete']
    else:
        return None


def main():
    output_folder_path = sys.argv[1]
    print(f'Output folder path: {output_folder_path}')
    output_dirs = [d for d in os.listdir(output_folder_path) if os.path.isdir(os.path.join(output_folder_path, d))]
    print('tile dir,tile count, percent complete')
    for output_dir in output_dirs:
        output_dir_path = os.path.join(output_folder_path, output_dir)
        tile_count = get_tile_count(output_dir_path)
        percent_complete = get_percent_complete(output_dir_path)
        print(f'{output_dir},{tile_count},{percent_complete}')


if __name__ == '__main__':
    main()

