import flask
from flask import request, Flask, jsonify
from flask_cors import CORS
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import io
import os
from pymongo import MongoClient
from extraction import extract_summarize_pdf

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

UPLOAD_FOLDER = './uploads/'

app = Flask(__name__)
CORS(app) 
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@app.route('/processFiles', methods=['POST'])
def get_drive_folder():
    data = flask.request.get_json()
    fileIds = data.get('fileIds', [])
    companyId = data.get('companyId')
    userId = data.get('userId')
    print(f'companyId: {companyId}')
    token_file = "token/token_{}.json".format(userId)
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'token/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    # Call the Drive v3 API
    service = build('drive', 'v3', credentials=creds)
    db = connectToMongoDB()
    for fileId in fileIds:
        print(f'Processing id: {id}')
        file_info = service.files().get(fileId=fileId, fields='id, name, parents, webViewLink, mimeType').execute()

        # Request the file content
        request_file_content = service.files().get_media(fileId=fileId)
        if file_info['mimeType'] == 'application/pdf':
            request = service.files().get_media(fileId=file_info['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()

            # Save the downloaded file in UPLOAD_FOLDER
            path = os.path.join(app.config['UPLOAD_FOLDER'], file_info['name'])
            with open(path, 'wb') as f:
                f.write(fh.getbuffer())

            persistDocumentMetaData(db, file_info["id"], file_info["name"], file_info["webViewLink"], companyId)
            print(f'PDF file {file_info["name"]} downloaded and saved at : {path}')

            extract_summarize_pdf(app.config['UPLOAD_FOLDER'], file_info['name'], companyId)

    return 'Files downloaded and saved from the folder', 200

@app.route('/listFiles', methods=['GET'])
def list_files():
    userId = request.args.get('userId')
    token_file = "token/token_{}.json".format(userId)
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    print(f'token_file {token_file}')
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'token/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    service = build('drive', 'v3', credentials=creds)

    results = service.files().list(
        pageSize=10, fields="nextPageToken, files(id, name, webViewLink)").execute()
    items = results.get('files', [])

    return jsonify(items)

def persistDocumentMetaData(db, documentId, docName, docUrl, companyId):
    MONGODB_URI =  "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
    try:
        collection = db['documents']

        # Define a document to be inserted
        document = {
            'docId': documentId,
            'docName': docName,
            'docUrl': docUrl,
            'companyId': companyId
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