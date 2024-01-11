from boxsdk import OAuth2, Client
from dotenv import dotenv_values
import os
import hashlib
import concurrent.futures

config = dotenv_values(".env")

auth = OAuth2(
    client_id=config["BOX_CLIENT_ID"],
    client_secret=config["BOX_CLIENT_SECRET"],
    access_token=config["BOX_ACCESS_TOKEN"],
)
client = Client(auth)


def get_local_file_sha1(file_path, chunk_size=8192):
    """
    Calculate the SHA1 checksum of a local file.

    :param file_path: Path to the local file.
    :param chunk_size: Chunk size to read the file.
    :return: SHA1 checksum of the file.
    """
    sha1 = hashlib.sha1()
    with open(file_path, 'rb') as file:
        while chunk := file.read(chunk_size):
            sha1.update(chunk)
    return sha1.hexdigest()


def download_file(file_id, download_folder_path, chunk_size=8192):
    """
    Download a given Box file.

    :param file_id: ID of the Box file to download.
    :param download_folder_path: Local path to save the downloaded file.
    :param chunk_size: Chunk size to read the file.
    """
    file = client.file(file_id=file_id).get()
    file_name = file.name
    file_path = os.path.join(download_folder_path, file_name)
    box_file_sha1 = file.sha1
    # Check if file exists and compare checksums
    if os.path.exists(file_path) and get_local_file_sha1(file_path, chunk_size) == box_file_sha1:
        print(f"File {file_name} already exists and is intact, skipping...", flush=True)
    else:
        print(f"Start downloading {file_name}...", flush=True)
        with open(file_path, 'wb') as file:
            client.file(file_id=file_id).download_to(file)
        print(f"Finished downloading {file_name}.", flush=True)

    file_size = os.path.getsize(file_path)
    return file_size


def download_folder(folder_id, download_folder_path):
    """
    Download the contents of a given Box folder.

    :param folder_id: ID of the Box folder to download.
    :param download_folder_path: Local path to save the downloaded files.
    """
    chunk_size = int(config['CHUNK_SIZE'])
    folder = client.folder(folder_id=folder_id).get()
    items = folder.get_items()

    max_workers = int(config['MAX_WORKERS'])  # Adjust the number of processes based on your needs
    file_id_list = []

    for item in items:
        if item.type == 'file':
            file_id_list.append(item.id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Start the load operations and mark each future with its file_id
        future_to_file_id = {executor.submit(download_file, file_id, download_folder_path, chunk_size):
                                 file_id for file_id in file_id_list}
        for future in concurrent.futures.as_completed(future_to_file_id):
            file_id = future_to_file_id[future]
            try:
                data = future.result()
            except Exception as exc:
                print('%r generated an exception: %s' % (file_id, exc), flush=True)
            else:
                print('File ID: %r size is %.2f GB' % (file_id, data/(1024 ** 3)), flush=True)


if __name__ == '__main__':

    folder_id = config["BOX_FOLDER_ID"]
    download_folder_path = config["DOWNLOAD_DIR"]

    # Create the local folder if it does not exist
    if not os.path.exists(download_folder_path):
        os.makedirs(download_folder_path)

    # Download the folder
    download_folder(folder_id, download_folder_path)
