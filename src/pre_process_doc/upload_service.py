import io
import os
import subprocess
import flask
import requests

from datetime import datetime
from enum import Enum
from flask import request, Flask, jsonify, make_response, url_for, render_template
from flask_cors import CORS
from flask_mail import Mail, Message
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pymongo import MongoClient
from logging_config import logger

# Local Python files
from extraction import process_pdf
from utility_functions import delete_user, delete_file, connect_to_mongodb, get_company_id, generate_confirmation_token, \
    confirm_token, get_shared_users, get_channel_id_by_name_and_company


# Define Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Define upload folder path
UPLOAD_FOLDER = './uploads/'

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
CORS(app)

app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER")
app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT"))
app.config['MAIL_USE_TLS'] = os.getenv("MAIL_USE_TLS").lower() in ['true', '1', 't', 'y', 'yes']
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER")

mail = Mail(app)


class DocumentStatus(Enum):
    IN_PROCESS = "IN_PROCESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def send_email(to, subject, template):
    msg = Message(
        subject,
        recipients=[to],
        html=template,
        sender=os.getenv('MAIL_DEFAULT_SENDER')
    )
    mail.send(msg)


@app.route('/emailConfirmation', methods=['POST'])
def trigger_email_confirmation():
    data = flask.request.get_json()
    user_id = data.get('userId')
    token = generate_confirmation_token(user_id)
    confirm_url = url_for('confirm_email', token=token, _external=True)
    html = render_template('activate.html', confirm_url=confirm_url)

    subject = "Please confirm your email"
    send_email(user_id, subject, html)
    data = {
        'message': f'Confirmation email has been send to {user_id}.'
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


def send_notification(user_id):
    chat_link = "/"
    user_ids = get_shared_users(user_id)

    for user_id in user_ids:
        # Generate the email content
        html = render_template('notification.html', chat_link=chat_link)

        # Subject of the email
        subject = "Your file has been processed"

        # Send the email
        send_email(user_id, subject, html)


@app.route('/comfirmEmail/<token>')
def confirm_email(token):
    email = confirm_token(token)
    db = connect_to_mongodb()
    collection = db['users']
    user = collection.find_one({"userId": email})
    if user:
        collection.update_one({"userId": email}, {"$set": {"isVerified": True}})
        return render_template('confirmed.html')
    else:
        logger.info('User not found or unable to update MongoDB.', 'danger')
        return render_template('expired.html')


# Function to delete the file data from vector DB and postgres database
@app.route('/deleteFile', methods=['POST'])
def delete_file_service():
    data = flask.request.get_json()
    file_id = data.get('fileId')
    user_id = data.get('userId')
    logger.info(f"File id is being deleted '{file_id}'")
    delete_file(user_id, file_id)
    data = {
        'message': 'File successfully deleted'
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


@app.route('/deleteUser', methods=['POST'])
def delete_user_service():
    data = flask.request.get_json()
    user_id = data.get('userId')
    logger.info(f"User id is being deleted '{user_id}'")
    delete_user(user_id)
    data = {
        'message': 'User successfully deleted'
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
    channel_name = data.get('channel_name')
    index_name = get_channel_id_by_name_and_company(db,channel_name, company_id)
    logger.info(f"Index name: {index_name}")
    creds = get_google_drive_credentials(user_id, "")
    service = build('drive', 'v3', credentials=creds)

    for file_id in file_ids:
        file_info = get_file_info(service, file_id)
        collection = db['documents']
        # Check if document already exists
        existing_document = collection.find_one({'docId': file_info['id']})
        if existing_document:
            status = existing_document['status']
            if status == "SUCCESS":
                continue
        logger.info(f"Processing file: {file_info['name']}")
        file_name = download_and_save_file(service, file_info)
        logger.info(f"File '{file_name}' downloaded and saved successfully")
        # Persist metadata with IN_PROCESS status
        persist_document_metadata(db, file_info, company_id, channel_name, DocumentStatus.IN_PROCESS)
        try:
            process_pdf(app.config['UPLOAD_FOLDER'], file_name, index_name, file_id)
            logger.info(f"File '{file_info['name']}' processed successfully")
            persist_document_metadata(db, file_info, company_id, channel_name, DocumentStatus.SUCCESS)
            logger.info(f"Metadata for file '{file_info['name']}' persisted successfully")
            send_notification(user_id)
        except Exception as e:
            logger.info(f"Error processing file: {file_info['name']}")
            logger.info(f"Error: {e}")
            # Update status to FAILURE on error
            persist_document_metadata(db, file_info, company_id, channel_name, DocumentStatus.FAILURE)

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
    logger.info(f"User id we are pulling the file for for file is '{user_id}'")
    creds = get_google_drive_credentials(user_id, code)
    service = build('drive', 'v3', credentials=creds)
    files = get_files_from_drive(service)
    logger.info("Files retrieved successfully from Google Drive")
    response = jsonify(files)
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response


@app.route('/getFilesForUser', methods=['GET'])
def get_file_status():
    try:
        user_id = request.args.get('userId')
        db = connect_to_mongodb()
        company_id = get_company_id(db, user_id)
        logger.info(f"Fetching file statuses for user: '{user_id}' and company: '{company_id}'")
        data = get_documents_by_company(db, company_id)
        jsonData = jsonify(data)
        response = make_response(jsonData)
        response.headers.add('Content-Type', 'application/json')
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except Exception as e:
        # Handle any exceptions that occur in the overall process
        logger.info(f"An error occurred in the file processing operation: {str(e)}")
        # Optionally, you can log the error or take other appropriate actions
        data = {
            'error': 'An error occurred during file processing'
        }
        response = jsonify(data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500


def get_documents_by_company(db, company_id):
    try:
        collection = db['documents']
        document_filter = {'companyId': company_id}
        projection = {'docId': 1, 'docName': 1, 'status': 1, '_id': 0,
                      'docUrl': 1}
        documents = collection.find(document_filter, projection)
        document_list = list(documents)
        return document_list  # Convert document list to JSON
    except Exception as e:
        logger.info(f'Failed to retrieve documents for company_id: {company_id}')
        logger.info(e)
        return '[]'  # Return empty JSON array in case of error


# Function to get users for a particular company
@app.route('/getSharedUsers', methods=['GET'])
def get_users():
    user_id = request.args.get('userId')
    user_ids = get_shared_users(user_id)
    response = jsonify({"userIds": user_ids})
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response


# Function to fetch files from Google Drive
def get_files_from_drive(service):
    try:
        q = "mimeType='application/pdf' or mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document' or mimeType='application/msword' or mimeType='application/vnd.openxmlformats-officedocument.presentationml.presentation' or mimeType='application/vnd.ms-powerpoint'"
        results = service.files().list(fields="nextPageToken, files(id, name, webViewLink)", q=q).execute()
        items = results.get('files', [])
        return items
    except Exception as e:
        logger.info("Failed to fetch files from Google Drive")
        logger.info(e)
        return []


# Function to fetch Google Drive credentials
def get_google_drive_credentials(user_id, code):
    db = connect_to_mongodb()

    result = fetch_token(db, user_id)
    if result:
        logger.info("found token in DB")
        token = result["token"]
        refresh_token = result["refresh_token"]

    else:
        logger.info("fetching token from google api")
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


# Function to connect to MongoDB
def connect_to_mongodb():
    try:
        MONGODB_URI = "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        logger.info("Connected successfully to MongoDB")
        return db
    except Exception as e:
        logger.info("Failed to connect to MongoDB")
        logger.info(e)


# Function to fetch file information from Google Drive
def get_file_info(service, file_id):
    return service.files().get(fileId=file_id, fields='id, name, parents, webViewLink, mimeType').execute()


# Function to download and save file from Google Drive
def download_and_save_file(service, file_info):
    if file_info['mimeType'] in ['application/pdf',
                                 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                 'application/msword',
                                 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                                 'application/vnd.ms-powerpoint']:  # Add MIME types for PPT and Word
        request = service.files().get_media(fileId=file_info['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        # Save the Word document to a temporary file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_info['name'])
        with open(file_path, 'wb') as f:
            f.write(fh.getbuffer())

        # Convert the Word document to PDF
        pdf_output_path = os.path.splitext(file_path)[0] + '.pdf'
        if file_info['mimeType'] in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                     'application/msword',
                                     'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                                     'application/vnd.ms-powerpoint']:
            subprocess.run(['unoconv', '-f', 'pdf', file_path])
            # Remove the temporary Word file
            os.remove(file_path)
        pdf_name = os.path.basename(pdf_output_path)
        return pdf_name


def get_company_id(db, user_id):
    try:
        collection = db['users']
        user = collection.find_one({"userId": user_id})
        if user:
            return user.get("companyId")
        else:
            return None
    except Exception as e:
        logger.info(f'Failed to get company id for user: {user_id}')
        logger.info(e)


# Function to persist document metadata into MongoDB
def persist_document_metadata(db, file_info, company_id, channel_id, status):
    try:
        collection = db['documents']
        # Check if document already exists
        existing_document = collection.find_one({'docId': file_info['id']})

        if existing_document:
            # Update status of existing document
            collection.update_one({'_id': existing_document['_id']}, {'$set': {'status': status.value}})
            logger.info(f"Updated status of document: {file_info['id']} to {status.value}")
        else:
            # Insert new document if it doesn't exist
            document = {
                'docId': file_info['id'],
                'docName': file_info['name'],
                'docUrl': file_info['webViewLink'],
                'companyId': company_id,
                'channelId': channel_id,
                'timestamp': datetime.now(),
                'status': status.value
            }
            collection.insert_one(document)
            logger.info(f"Inserted document: {file_info['id']} with status {status.value}")
    except Exception as e:
        logger.info(f'Failed to persist document: {file_info["id"]}')
        logger.info(e)


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
            logger.info("POST request successful!")
            data = response.json()
            return data
        else:
            logger.info("POST request failed with status code:", response.status_code)
    except Exception as e:
        logger.info("An error occurred:", str(e))


def fetch_token(db, userId):
    try:
        collection = db['user_token']

        # Define a document to be inserted
        query = {"user_id": userId}
        projection = {"user_id", "token", "refresh_token"}  # You can specify fields to include or exclude in the result
        result = collection.find_one(query, projection)
        if result:
            logger.info(f'found code for user: {result.get("user_id")}')
            return result
        else:
            logger.info(f'No token found for user: {userId}, persisting token')
    except Exception as e:
        logger.info(f'Failed to fetch token for user: {userId}')
        logger.info(e)


def persist_token(db, userId, token, refresh_token):
    try:
        collection = db['user_token']

        # Define a document to be inserted
        query = {"user_id": userId}
        projection = {"user_id", "token", "refresh_token"}  # You can specify fields to include or exclude in the result
        result = collection.find_one(query, projection)
        if result:
            logger.info(f'found code for user: {result.get("user_id")}')
        else:
            logger.info(f'No token found for user: {userId}, persisting token')
            document = {
                'user_id': userId,
                'token': token,
                'refresh_token': refresh_token
            }
            collection.insert_one(document)
    except Exception as e:
        logger.info(f'Failed to fetch token for user: {userId}')
        logger.info(e)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
