from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import io
import os
from flask import Flask, request, send_file
from pymongo import MongoClient
from extraction import extract_summarize_pdf

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

UPLOAD_FOLDER = './uploads/'

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
    results = service.files().list(fields='files(id, name, parents, webViewLink, mimeType )', q=f"'{folder_id}' in parents").execute()
    items = results.get('files', [])
    db = connectToMongoDB()

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

                persistDocumentMetaData(db, item["id"], item["name"], item["webViewLink"], folder_id)
                print(f'PDF file {item["name"]} downloaded and saved at : {path}')
                extract_summarize_pdf(app.config['UPLOAD_FOLDER'], item['name'])

    return 'Files downloaded and saved from the folder', 200

def persistDocumentMetaData(db, documentId, docName, docUrl, folder):
    MONGODB_URI =  "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
    try:
        collection = db['documents']

        # Define a document to be inserted
        document = {
            'docId': documentId,
            'docName': docName,
            'docUrl': docUrl,
            'parentFolder': folder
        }

        # Insert the document into the collection
        insert_result = collection.insert_one(document)
        print(f'Inserted doc: {documentId} to documents collection')
    except Exception as e:
        print(f'Failed to insert doc: {documentId} to documents collection')
        print(e)

def connectToMongoDB():
    MONGODB_URI = "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
    try:
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        print("Connected successfully")
        return db
    except Exception as e:
        print("Failed to connect to MongoDB")
        print(e)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)