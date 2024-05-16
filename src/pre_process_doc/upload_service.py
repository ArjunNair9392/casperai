import flask
import io
import os

from datetime import datetime
from extraction import process_pdf
from flask_cors import CORS
from flask import request, Flask, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from pymongo import MongoClient
from utility_functions import delete_file, connect_to_mongodb, get_company_id
import requests

# Define Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Define upload folder path
UPLOAD_FOLDER = './uploads/'

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
CORS(app)

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Function to delete the file data from vector DB and postgres database
@app.route('/deleteFile', methods=['POST'])
def delete_file_service():
    data = flask.request.get_json()
    file_id = data.get('fileId')
    user_id = data.get('userId')
    print(f"File id is being deleted '{file_id}'")
    delete_file(user_id, file_id)
    data = {
        'message': 'File successfully deleted'
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200

# Function to handle processing files from Google Drive
@app.route('/processFiles', methods=['POST'])
def process_files():
    db = connect_to_mongodb()
    data = flask.request.get_json()
    file_ids = data.get('fileIds', [])
    user_id = data.get('userId')
    company_id = get_company_id(db, user_id)
    creds = get_google_drive_credentials(user_id, "")
    service = build('drive', 'v3', credentials=creds)

    for file_id in file_ids:
        file_info = get_file_info(service, file_id)
        print(f"Processing file: {file_info['name']}")
        download_and_save_file(service, file_info)
        print(f"File '{file_info['name']}' downloaded and saved successfully")
        process_pdf(app.config['UPLOAD_FOLDER'], file_info['name'], company_id, file_id)
        print(f"File '{file_info['name']}' processed successfully")
        persist_document_metadata(db, file_info, company_id, True)
        print(f"Metadata for file '{file_info['name']}' persisted successfully")

    data = {
        'message': 'Files downloaded and saved from the folder'
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200

# Function to list files from Google Drive
@app.route('/listFiles', methods=['GET'])
def list_files():
    user_id = request.args.get('userId')
    code = request.args.get('code')
    print(f"User id we are pulling the file for for file is '{user_id}'")
    creds = get_google_drive_credentials(user_id, code)
    service = build('drive', 'v3', credentials=creds)
    files = get_files_from_drive(service)
    print("Files retrieved successfully from Google Drive")
    response = jsonify(files)
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response

# Function to fetch files from Google Drive
def get_files_from_drive(service):
    try:
        results = service.files().list(fields="nextPageToken, files(id, name, webViewLink)", q="mimeType='application/pdf'").execute()
        items = results.get('files', [])
        return items
    except Exception as e:
        print("Failed to fetch files from Google Drive")
        print(e)
        return []

# Function to fetch Google Drive credentials
def get_google_drive_credentials(user_id, code):
    db = connect_to_mongodb()

    result = fetch_token(db, user_id)
    if result:
        print("found token in DB")
        token = result["token"]
        refresh_token = result["refresh_token"]

    else:
        print("fetching token from google api")
        token_result = get_token(code)
        token = token_result.get("access_token")
        refresh_token = token_result.get("refresh_token")
        persist_token(db, user_id, token, refresh_token)

    creds = Credentials(
            token=token,
            refresh_token=refresh_token,
            token_uri="https://www.googleapis.com/oauth2/v3/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        )
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

    return creds

# Function to refresh Google Drive credentials
def refresh_credentials(token_file):
    flow = InstalledAppFlow.from_client_secrets_file('token/credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_file, 'w') as token:
        token.write(creds.to_json())
    return creds

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

def get_token(code):
    try:
        url = "https://oauth2.googleapis.com/token"
        params = {
            "code": code,
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "redirect_uri": "http://localhost:8080/usable/folders"
        }
        response = requests.post(url, params=params)
        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            print("POST request successful!")
            data =response.json()
            return data
        else:
            print("POST request failed with status code:", response.status_code)
    except Exception as e:
        print("An error occurred:", str(e))

def fetch_token(db, userId):
    try:
        collection = db['user_token']

        # Define a document to be inserted
        query = {"user_id": userId}
        projection = {"user_id", "token", "refresh_token"}   # You can specify fields to include or exclude in the result
        result = collection.find_one(query, projection)
        if result:
            print(f'found code for user: {result.get("user_id")}')
            return result
        else:
            print(f'No token found for user: {userId}, persisting token')
    except Exception as e:
        print(f'Failed to fetch token for user: {userId}')
        print(e)

def persist_token(db, userId, token, refresh_token):
    try:
        collection = db['user_token']

        # Define a document to be inserted
        query = {"user_id": userId}
        projection = {"user_id", "token", "refresh_token"}  # You can specify fields to include or exclude in the result
        result = collection.find_one(query, projection)
        if result:
            print(f'found code for user: {result.get("user_id")}')
        else:
            print(f'No token found for user: {userId}, persisting token')
            document = {
                'user_id': userId,
                'token': token,
                'refresh_token': refresh_token
            }
            collection.insert_one(document)
    except Exception as e:
        print(f'Failed to fetch token for user: {userId}')
        print(e)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)


    