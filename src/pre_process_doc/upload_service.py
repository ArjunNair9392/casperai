import flask
import io
import os

from datetime import datetime
from extraction import process_pdf
from flask import request, Flask, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from pymongo import MongoClient

# Define Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Define upload folder path
UPLOAD_FOLDER = './uploads/'

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Function to handle processing files from Google Drive
@app.route('/processFiles', methods=['POST'])
def process_files():
    data = flask.request.get_json()
    file_ids = data.get('fileIds', [])
    company_id = data.get('companyId')
    user_id = data.get('userId')
    creds = get_google_drive_credentials(user_id)
    service = build('drive', 'v3', credentials=creds)
    db = connect_to_mongodb()

    for file_id in file_ids:
        file_info = get_file_info(service, file_id)
        print(f"Processing file: {file_info['name']}")
        download_and_save_file(service, file_info)
        print(f"File '{file_info['name']}' downloaded and saved successfully")
        process_pdf(app.config['UPLOAD_FOLDER'], file_info['name'], company_id)
        print(f"File '{file_info['name']}' processed successfully")
        persist_document_metadata(db, file_info, company_id, True)
        print(f"Metadata for file '{file_info['name']}' persisted successfully")

    return 'Files downloaded and saved from the folder', 200

# Function to list files from Google Drive
@app.route('/listFiles', methods=['GET'])
def list_files():
    user_id = request.args.get('userId')
    print(f"User id we are pulling the file for for file is '{user_id}'")
    creds = get_google_drive_credentials(user_id)
    service = build('drive', 'v3', credentials=creds)
    files = get_files_from_drive(service)
    print("Files retrieved successfully from Google Drive")
    return jsonify(files)

# Function to fetch files from Google Drive
def get_files_from_drive(service):
    try:
        results = service.files().list(pageSize=10, fields="nextPageToken, files(id, name, webViewLink)").execute()
        items = results.get('files', [])
        return items
    except Exception as e:
        print("Failed to fetch files from Google Drive")
        print(e)
        return []

# Function to fetch Google Drive credentials
def get_google_drive_credentials(user_id):
    token_file = f"token/token_{user_id}.json"
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = refresh_credentials(token_file)

    return creds

# Function to refresh Google Drive credentials
def refresh_credentials(token_file):
    flow = InstalledAppFlow.from_client_secrets_file('token/credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_file, 'w') as token:
        token.write(creds.to_json())
    return creds

# Function to connect to MongoDB
def connect_to_mongodb():
    try:
        MONGODB_URI =  "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        print("Connected successfully to MongoDB")
        return db
    except Exception as e:
        print("Failed to connect to MongoDB")
        print(e)

# Function to fetch file information from Google Drive
def get_file_info(service, file_id):
    return service.files().get(fileId=file_id, fields='id, name, parents, webViewLink, mimeType').execute()

# Function to download and save file from Google Drive
def download_and_save_file(service, file_info):
    if file_info['mimeType'] == 'application/pdf':
        request = service.files().get_media(fileId=file_info['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        path = os.path.join(app.config['UPLOAD_FOLDER'], file_info['name'])
        with open(path, 'wb') as f:
            f.write(fh.getbuffer())

# Function to persist document metadata into MongoDB
def persist_document_metadata(db, file_info, company_id, processed=False):
    try:
        collection = db['documents']
        document = {
            'docId': file_info['id'],
            'docName': file_info['name'],
            'docUrl': file_info['webViewLink'],
            'companyId': company_id,
            'timestamp': datetime.now(),
            'processed': processed
        }
        collection.insert_one(document)
    except Exception as e:
        print(f'Failed to insert document: {file_info["id"]} to documents collection')
        print(e)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)