from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import io
import os
from flask import Flask, request, send_file
from extraction import extract_summarize_pdf

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

UPLOAD_FOLDER = '/Users/arjunnair/Workspace/casperai/src/pre_process_doc/uploads/'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/get-drive-folder/<folder_id>', methods=['GET'])
def get_drive_folder(folder_id):
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                '/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # Call the Drive v3 API
    service = build('drive', 'v3', credentials=creds)

    # List all files in the folder
    results = service.files().list(q=f"'{folder_id}' in parents").execute()
    items = results.get('files', [])

    if not items:
        print('No files found.')
    else:
        for item in items:
            # Only download files that are pdfs
            if item['mimeType'] == 'application/pdf':
                request = service.files().get_media(fileId=item['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()

                # Save the downloaded file in UPLOAD_FOLDER
                path = os.path.join(app.config['UPLOAD_FOLDER'], item['name'])
                with open(path, 'wb') as f:
                    f.write(fh.getbuffer())

                print(f'PDF file {item["name"]} downloaded and saved at : {path}')
                extract_summarize_pdf(app.config['UPLOAD_FOLDER'], item['name'])

    return 'Files downloaded and saved from the folder', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)