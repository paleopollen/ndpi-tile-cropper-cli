from boxsdk import OAuth2, Client
from dotenv import dotenv_values
import os
import hashlib

config = dotenv_values(".env")

auth = OAuth2(
    client_id=config["BOX_CLIENT_ID"],
    client_secret=config["BOX_CLIENT_SECRET"],
    access_token=config["BOX_ACCESS_TOKEN"],
)
client = Client(auth)

user = client.user().get()
print(f'The current user ID is {user.id}')


def get_local_file_sha1(file_path):
    """
    Calculate the SHA1 checksum of a local file.

    :param file_path: Path to the local file.
    :return: SHA1 checksum of the file.
    """
    sha1 = hashlib.sha1()
    with open(file_path, 'rb') as file:
        while True:
            data = file.read(int(config['CHUNK_SIZE']))
            if not data:
                break
            sha1.update(data)
    return sha1.hexdigest()


def download_folder(folder_id, download_folder_path):
    """
    Download the contents of a given Box folder.

    :param folder_id: ID of the Box folder to download.
    :param download_folder_path: Local path to save the downloaded files.
    """
    folder = client.folder(folder_id=folder_id).get()
    items = folder.get_items()
    for item in items:
        if item.type == 'file':
            file_name = item.name
            file_path = os.path.join(download_folder_path, file_name)
            box_file_sha1 = item.sha1
            # Check if file exists and compare checksums
            if os.path.exists(file_path) and get_local_file_sha1(file_path) == box_file_sha1:
                print(f"File {item.name} already exists and is intact, skipping...")
            else:
                print(f"Start downloading {file_name}...")
                with open(file_path, 'wb') as file:
                    client.file(file_id=item.id).download_to(file)
                print(f"Finished downloading {file_name}.")
        elif item.type == 'folder':
            new_folder_path = os.path.join(download_folder_path, item.name)
            os.makedirs(new_folder_path, exist_ok=True)
            download_folder(item.id, new_folder_path)


folder_id = config["BOX_FOLDER_ID"]
download_folder_path = config["DOWNLOAD_DIR"]

# Create the local folder if it does not exist
if not os.path.exists(download_folder_path):
    os.makedirs(download_folder_path)

# Download the folder
download_folder(folder_id, download_folder_path)
