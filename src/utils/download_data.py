from boxsdk import OAuth2, Client
from dotenv import dotenv_values
import os

config = dotenv_values(".env")

auth = OAuth2(
    client_id=config["BOX_CLIENT_ID"],
    client_secret=config["BOX_CLIENT_SECRET"],
    access_token=config["BOX_ACCESS_TOKEN"],
)
client = Client(auth)

user = client.user().get()
print(f'The current user ID is {user.id}')

folder_path = os.path.join("PAL1999", "C3")
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

with open(os.path.join(folder_path, config["FILENAME"]), "wb") as file:
    client.file(file_id=config["FILE_ID"]).download_to(file)