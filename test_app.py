import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Đọc file service account
with open('service-account.json', 'r') as f:
    service_account_info = json.load(f)

credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=['https://www.googleapis.com/auth/drive.file']
)

service = build('drive', 'v3', credentials=credentials)

# Tạo file test
with open('test.txt', 'w') as f:
    f.write('Test content')

# Upload
file_metadata = {
    'name': 'test.txt',
    'parents': ['12YVdRdU5HXlaav9n3itwe8mhVm_bnFJW']
}
media = MediaFileUpload('test.txt', mimetype='text/plain')
file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
print(f"File ID: {file.get('id')}")