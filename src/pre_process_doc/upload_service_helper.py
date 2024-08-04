import io
import os
import subprocess
from datetime import datetime

import psycopg2
import requests
from bson import ObjectId
from flask import render_template
from flask_mail import Message
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaIoBaseDownload
from itsdangerous import URLSafeTimedSerializer
from pinecone import Pinecone
from pymongo import MongoClient

from logging_config import logger

# Define Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


# Function to connect to MongoDB
def connect_to_mongodb():
    try:
        MONGODB_URI = ("mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w"
                       "=majority&appName=Cluster0")
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        logger.info("Connected successfully to MongoDB")
        return db
    except Exception as e:
        logger.info("Failed to connect to MongoDB")
        logger.info(e)


def get_company_id(db, user_email):
    try:
        collection = db['users']
        user = collection.find_one({"user_email": user_email})
        if user:
            return user.get("company_id")
        else:
            return None
    except Exception as e:
        logger.info(f'Failed to get company id for user: {user_email}')
        logger.info(e)


def query_records_by_metadata(index, metadata_key, metadata_value, namespace=''):
    query_result = index.query(
        vector=[0] * 1536,  # A dummy vector since we only need metadata filtering
        filter={metadata_key: {'$eq': metadata_value}},
        top_k=10000,  # Adjust as necessary, maximum is 10000
        namespace=namespace,
        include_metadata=True
    )
    return query_result['matches']


def delete_records_from_vectordb(index, ids, namespace=''):
    index.delete(ids=ids, namespace=namespace)


def delete_records_from_postgres(custom_ids):
    db_params = {
        "host": os.getenv("POSTGRES_HOST_IP"),
        "port": os.getenv("POSTGRES_PORT"),
        "database": os.getenv("POSTGRES_DB_NAME"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }
    try:
        # Connect to the PostgreSQL database
        connection = psycopg2.connect(**db_params)

        # Create a cursor object
        cursor = connection.cursor()

        # Create the DELETE query
        delete_query = "DELETE FROM documents WHERE doc_id = ANY(%s)"

        # Execute the DELETE query for the array of custom_ids
        cursor.execute(delete_query, (custom_ids,))

        # Commit the transaction
        connection.commit()

        # Close the cursor and connection
        cursor.close()
        connection.close()

        logger.info("Records deleted successfully")

    except (Exception, psycopg2.Error) as error:
        logger.info("Error while deleting records from PostgreSQL:", error)


def delete_records_from_mongodb(file_id):
    db = connect_to_mongodb()
    result = db.documents.delete_one({"doc_id": file_id})
    logger.info(f"Deleted {result.deleted_count} records from MongoDB.")


def delete_file(file_id, user_email, channel_name):
    db = connect_to_mongodb()
    company_id = get_company_id(db, user_email)
    logger.info(f"Company ID: {company_id}")
    channel_id = get_channel_id(db, channel_name, company_id)
    print("channel_id: ", channel_id)
    delete_records_from_mongodb(file_id)
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(channel_id)
    records = query_records_by_metadata(index, 'file_id', file_id)
    # Extract IDs from the query result
    record_ids = [record['id'] for record in records]
    doc_ids = [record['metadata']['doc_id'] for record in records]
    delete_records_from_postgres(doc_ids)
    logger.info("Records deleted from PostgreSQL.")
    # Delete the records
    delete_records_from_vectordb(index, record_ids)
    logger.info("Records deleted from vector database.")


def delete_user(user_id):
    db = connect_to_mongodb()
    result = db.users.delete_many({"userId": user_id})
    logger.info(f"User ID: {user_id}")
    logger.info(f"Deleted {result.deleted_count} records from MongoDB.")


def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(os.getenv("MAIL_SECRET_KEY"))
    return serializer.dumps(email, salt=os.getenv('MAIL_SECURITY_PASSWORD_SALT'))


def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(os.getenv("MAIL_SECRET_KEY"))
    try:
        email = serializer.loads(
            token,
            salt=os.getenv('MAIL_SECURITY_PASSWORD_SALT'),
            max_age=expiration
        )
    except:
        return False
    return email


def get_channel_members(user_email, channel_name):
    db = connect_to_mongodb()
    channels_collection = db['channels']
    users_collection = db['users']
    user = users_collection.find_one({"user_email": user_email})
    channel = channels_collection.find_one({
        'channel_name': channel_name,
        'company_id': user['company_id']
    })
    # Convert member_ids to ObjectId and store in a list
    member_ids = channel['member_ids']

    # Initialize an array to store user emails
    user_emails = []

    # Loop through member_ids and find the corresponding user
    for member_id in member_ids:
        user = users_collection.find_one({"_id": member_id})
        if user and 'user_email' in user:
            user_emails.append(user['user_email'])

    return user_emails


def get_channel_id(db, channel_name, company_id):
    try:
        collection = db['channels']
        channel = collection.find_one({
            'channel_name': channel_name,
            'company_id': company_id
        }, {'_id': 1})  # Only retrieve the _id field
        if channel:
            return str(channel.get('_id'))
        else:
            return None
    except Exception as e:
        print(f'Failed to get channel id for channel: {channel_name} and company: {company_id}')
        print(e)
        return None


def get_documents_by_channel(db, channel_id):
    try:
        collection = db['documents']
        document_filter = {'channel_id': channel_id}
        projection = {'doc_id': 1, 'doc_name': 1, 'status': 1, '_id': 0,
                      'doc_url': 1}
        documents = collection.find(document_filter, projection)
        document_list = list(documents)
        return document_list  # Convert document list to JSON
    except Exception as e:
        logger.info(f'Failed to retrieve documents for company_id: {channel_id}')
        logger.info(e)
        return '[]'  # Return empty JSON array in case of error


# Function to fetch files from Google Drive
def get_files_from_drive(service):
    try:
        q = ("mimeType='application/pdf' or mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml"
             ".document' or mimeType='application/msword' or "
             "mimeType='application/vnd.openxmlformats-officedocument.presentationml.presentation' or "
             "mimeType='application/vnd.ms-powerpoint'")
        results = service.files().list(fields="nextPageToken, files(id, name, webViewLink)", q=q).execute()
        items = results.get('files', [])
        return items
    except Exception as e:
        logger.info("Failed to fetch files from Google Drive")
        logger.info(e)
        return []


# Function to fetch Google Drive credentials
def get_google_drive_credentials(user_email, code):
    db = connect_to_mongodb()

    result = fetch_token(db, user_email)
    if result:
        logger.info("found token in DB")
        token = result["token"]
        refresh_token = result["refresh_token"]

    else:
        logger.info("fetching token from google api")
        token_result = get_token(code)
        token = token_result.get("access_token")
        refresh_token = token_result.get("refresh_token")
        persist_token(db, user_email, token, refresh_token)

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
def download_and_save_file(service, file_info, app):
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


# Function to persist document metadata into MongoDB
def persist_document_metadata(db, file_info, channel_id, status):
    try:
        collection = db['documents']
        # Check if document already exists
        existing_document = collection.find_one({'doc_id': file_info['id']})

        if existing_document:
            # Update status of existing document
            collection.update_one({'_id': existing_document['_id']}, {'$set': {'status': status.value}})
            logger.info(f"Updated status of document: {file_info['id']} to {status.value}")
        else:
            # Insert new document if it doesn't exist
            document = {
                'doc_id': file_info['id'],
                'doc_name': file_info['name'],
                'doc_url': file_info['webViewLink'],
                'channel_id': channel_id,
                'status': status.value,
                'timestamp': datetime.now()
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


def fetch_token(db, user_email):
    try:
        collection = db['user_token']

        # Define a document to be inserted
        query = {"user_email": user_email}
        projection = {"user_email", "token",
                      "refresh_token"}  # You can specify fields to include or exclude in the result
        result = collection.find_one(query, projection)
        if result:
            logger.info(f'found code for user: {result.get("user_email")}')
            return result
        else:
            logger.info(f'No token found for user: {user_email}, persisting token')
    except Exception as e:
        logger.info(f'Failed to fetch token for user: {user_email}')
        logger.info(e)


def persist_token(db, user_email, token, refresh_token):
    try:
        collection = db['user_token']

        # Define a document to be inserted
        query = {"user_email": user_email}
        projection = {"user_email", "token",
                      "refresh_token"}  # You can specify fields to include or exclude in the result
        result = collection.find_one(query, projection)
        if result:
            logger.info(f'found code for user: {result.get("user_email")}')
        else:
            logger.info(f'No token found for user: {user_email}, persisting token')
            document = {
                'user_email': user_email,
                'token': token,
                'refresh_token': refresh_token
            }
            collection.insert_one(document)
    except Exception as e:
        logger.info(f'Failed to fetch token for user: {user_email}')
        logger.info(e)


def send_email(to, subject, template, mail):
    msg = Message(
        subject,
        recipients=[to],
        html=template,
        sender=os.getenv('MAIL_DEFAULT_SENDER')
    )
    mail.send(msg)


def send_notification(user_email, mail, channel_id):
    chat_link = "/"
    user_emails = get_channel_members(channel_id)

    for user_id in user_emails:
        # Generate the email content
        html = render_template('notification.html', chat_link=chat_link)

        # Subject of the email
        subject = "Your file has been processed"

        # Send the email
        send_email(user_id, subject, html, mail)
