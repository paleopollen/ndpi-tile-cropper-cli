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

