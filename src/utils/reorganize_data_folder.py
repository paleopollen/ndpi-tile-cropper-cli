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

# This program re-organizes files in a folder to multiple sub-folders, and display the sub-folder paths.

# usage: reorganize_data_folder.py [-h] --src SRC --dst DST --num NUM
#
# Reorganize files in a folder to multiple sub-folders
#
# options:
#   -h, --help  show this help message and exit
#   --src SRC   source folder path
#   --dst DST   destination folder path
#   --num NUM   number of sub-folders to create

# Example:
# python reorganize_data_folder.py --src /path/to/source --dst /path/to/destination --num 5

class ReOrganizer:
    from argparse import ArgumentParser

    parser = ArgumentParser(description='Reorganize files in a folder to multiple sub-folders')
    parser.add_argument('--src', '-s', type=str, help='source folder path', required=True)
    parser.add_argument('--dst', '-d', type=str, help='destination folder path', required=True)
    parser.add_argument('--num', '-n', type=int, help='number of sub-folders to create', required=True)
    args = parser.parse_args()

    def __init__(self, src, dst, num):
        self.src = src
        self.dst = dst
        self.num = num

    def reorganize(self):
        import os
        import shutil

        if not os.path.exists(self.dst):
            os.makedirs(self.dst)

        files = os.listdir(self.src)
        sorted(files)

        for i in range(self.num):
            folder = os.path.join(self.dst, str(i))
            os.makedirs(folder)
            for j in range(i, len(files), self.num):
                shutil.move(os.path.join(self.src, files[j]), folder)

        for i in range(self.num):
            print(os.path.join(self.dst, str(i)))


if __name__ == '__main__':
    re_organizer = ReOrganizer(ReOrganizer.args.src, ReOrganizer.args.dst, ReOrganizer.args.num)
    re_organizer.reorganize()
