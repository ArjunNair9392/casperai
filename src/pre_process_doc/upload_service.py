import os
import os
from enum import Enum

import flask
from flask import request, Flask, jsonify, make_response, url_for, render_template
from flask_cors import CORS
from flask_mail import Mail
from googleapiclient.discovery import build

# Local Python files
from extraction import process_pdf
from logging_config import logger
from upload_service_helper import delete_user, delete_file, connect_to_mongodb, get_company_id, \
    generate_confirmation_token, confirm_token, get_channel_members, get_channel_id, get_documents_by_channel, \
    get_google_drive_credentials, get_file_info, download_and_save_file, persist_document_metadata, \
    get_files_from_drive, send_notification, send_email

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


# Function to handle processing files from Google Drive
@app.route('/process-files', methods=['POST'])
def process_files():
    db = connect_to_mongodb()
    data = flask.request.get_json()
    file_ids = data.get('file_ids', [])
    user_email = data.get('user_email')
    channel_name = data.get('channel_name')
    company_id = get_company_id(db, user_email)

    # channel_id is the index name tied to pinecone index
    channel_id = get_channel_id(db, channel_name, company_id)
    logger.info(f"Index name: {channel_id}")
    creds = get_google_drive_credentials(user_email, "")
    service = build('drive', 'v3', credentials=creds)

    for file_id in file_ids:
        file_info = get_file_info(service, file_id)
        collection = db['documents']
        # Check if document already exists
        existing_document = collection.find_one({'doc_id': file_info['id']})
        if existing_document:
            status = existing_document['status']
            if status == "SUCCESS":
                continue
        logger.info(f"Processing file: {file_info['name']}")
        file_name = download_and_save_file(service, file_info, app)
        logger.info(f"File '{file_name}' downloaded and saved successfully")
        # Persist metadata with IN_PROCESS status
        persist_document_metadata(db, file_info, channel_id, DocumentStatus.IN_PROCESS)
        try:
            process_pdf(app.config['UPLOAD_FOLDER'], file_name, channel_id, file_id)
            logger.info(f"File '{file_info['name']}' processed successfully")
            persist_document_metadata(db, file_info, channel_id, DocumentStatus.SUCCESS)
            logger.info(f"Metadata for file '{file_info['name']}' persisted successfully")
            send_notification(user_email, mail, channel_id)
        except Exception as e:
            logger.info(f"Error processing file: {file_info['name']}")
            logger.info(f"Error: {e}")
            # Update status to FAILURE on error
            persist_document_metadata(db, file_info, channel_id, DocumentStatus.FAILURE)

    data = {
        'message': 'Files downloaded and saved from the folder'
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


# Function to list files from Google Drive
@app.route('/list-files-from-gdrive', methods=['GET'])
def list_files():
    user_email = request.args.get('user_email')
    code = request.args.get('code')
    logger.info(f"User id we are pulling the file for for file is '{user_email}'")
    creds = get_google_drive_credentials(user_email, code)
    service = build('drive', 'v3', credentials=creds)
    files = get_files_from_drive(service)
    logger.info("Files retrieved successfully from Google Drive")
    response = jsonify(files)
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response


@app.route('/list-files-from-channel', methods=['GET'])
def get_file_status():
    try:
        user_email = request.args.get('user_email')
        channel_name = request.args.get('channel_name')
        db = connect_to_mongodb()
        company_id = get_company_id(db, user_email)
        channel_id = get_channel_id(db, channel_name, company_id)
        logger.info(
            f"Fetching file statuses for user: '{user_email}', company: '{company_id}' and channel: '{channel_id}'")
        data = get_documents_by_channel(db, channel_id)
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


# Function to get users for a particular company
@app.route('/get-channel-members', methods=['GET'])
def get_users():
    channel_name = request.args.get('channel_name')
    user_email = request.args.get('channel_name')
    user_ids = get_channel_members(user_email, channel_name)
    response = jsonify({"userIds": user_ids})
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response


@app.route('/email-confirmation', methods=['POST'])
def trigger_email_confirmation():
    data = flask.request.get_json()
    user_email = data.get('user_email')
    token = generate_confirmation_token(user_email)
    confirm_url = url_for('confirm_email', token=token, _external=True)
    html = render_template('activate.html', confirm_url=confirm_url)

    subject = "Please confirm your email"
    send_email(user_email, subject, html, mail)
    data = {
        'message': f'Confirmation email has been send to {user_email}.'
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


@app.route('/confirm-email/<token>')
def confirm_email(token):
    user_email = confirm_token(token)
    db = connect_to_mongodb()
    collection = db['users']
    user = collection.find_one({"user_email": user_email})
    if user:
        collection.update_one({"user_email": user_email}, {"$set": {"is_verified": True}})
        return render_template('confirmed.html')
    else:
        logger.info('User not found or unable to update MongoDB.', 'danger')
        return render_template('expired.html')


# Function to delete the file data from vector DB and postgres database
@app.route('/delete-file', methods=['POST'])
def delete_file_service():
    data = flask.request.get_json()
    file_id = data.get('file_id')
    user_email = data.get('user_email')
    channel_name = data.get('channel_name')
    logger.info(f"File id is being deleted '{file_id}'")
    delete_file(file_id, user_email, channel_name)
    data = {
        'message': 'File successfully deleted'
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


# TODO: Do we still need this?
@app.route('/delete-user', methods=['POST'])
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
