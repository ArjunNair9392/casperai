import os
import requests
import slack

from datetime import datetime

from bson import ObjectId
from pymongo import MongoClient
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaIoBaseDownload
from logging_config import logger
from slack_sdk import WebClient


def get_company_for_user(db, user_email):
    try:
        user_collection = db['users']
        user = user_collection.find_one({"user_email": user_email})
        company_id = user['company_id']

        company_obj_id = ObjectId(company_id)
        company_collection = db['companies']
        query = {"_id": company_obj_id}
        company = company_collection.find_one(query)

        if company:
            print(f'Company for admin: {company.get("admin_email")}')
            return company
        else:
            print(f'Company not found for admin: {user_email}')
    except Exception as e:
        print(f'Failed to fetch company not found for admin: {user_email}')
        print(e)
    return company


def persist_company_info(db, name, address, city, state, country, phone_number, admin_email):
    try:
        collection = db['companies']
        document = {
            'name': name,
            'address': address,
            'city': city,
            'state': state,
            'country': country,
            'phone_number': phone_number,
            'admin_email': admin_email,
            'timestamp': datetime.now(),
        }
        insert_result = collection.insert_one(document)
        print(f'Inserted company info for : {name}')
        company_id = str(insert_result.inserted_id)
    except Exception as e:
        print(f'Failed to insert company info for : {name}')
        print(e)
    return company_id


def persist_channel_info(db, channel_name, company_id, admin_email, slack_workspace):
    try:
        collection = db['channels']
        existing_document = collection.find_one({'channel_name': channel_name, 'company_id': company_id})
        users_collection = db['users']
        user = users_collection.find_one({"user_email": admin_email})
        if not existing_document:
            document = {
                'channel_name': channel_name,
                'company_id': company_id,
                'admin_email': admin_email,
                'member_ids': [str(user['_id'])],
                'slack_channel_id': '',
                'slack_workspace': slack_workspace,
                'timestamp': datetime.now(),
            }
            insert_result = collection.insert_one(document)
            generated_id = insert_result.inserted_id
            print(f'Inserted channel info for: {channel_name}, {company_id}')
            return insert_result
        else:
            return existing_document
    except Exception as e:
        print(f'Failed to insert channel info for: {channel_name}, {company_id}')
        print(e)
        return None


def add_slack_channel(channel, slack_user_id, user_email, team_id):
    try:
        # Connect to the database
        db = connect_to_mongodb()
        workspaces_collection = db['workspaces']

        # Fetch the access token for the given workspace (team_name)
        workspace = workspaces_collection.find_one({"team_id": team_id})
        if not workspace:
            print(f"Workspace with name {team_id} not found.")
            return

        # Retrieve the access token for the workspace
        access_token = workspace.get("access_token")
        if not access_token:
            print(f"Access token for workspace {team_id} is missing.")
            return

        # Initialize the Slack client with the access token for this workspace
        slack_user_client = WebClient(token=access_token)

        # Check if the Slack channel already has an ID
        if channel.get('slack_channel_id') == "":
            try:
                # Create a private Slack channel with a name based on channel_name
                channel_name = f"ask_{channel['channel_name'].replace(' ', '_').lower()}"
                response = slack_user_client.conversations_create(
                    name=channel_name,
                    is_private=True
                )
                slack_channel_id = response["channel"]["id"]

                # Invite the bot and user to the private channel
                slack_user_client.conversations_invite(
                    channel=slack_channel_id,
                    users=slack_user_id
                )

                # Check if the user is already a member of the channel
                channel_info = slack_user_client.conversations_members(channel=slack_channel_id)
                if slack_user_id not in channel_info["members"]:
                    slack_user_client.conversations_invite(
                        channel=slack_channel_id,
                        users=slack_user_id
                    )
                else:
                    print(f"User {user_email} is already a member of the channel {channel_name}.")

                # Update the database to store the Slack channel ID
                channel.update_one(
                    {"_id": channel['_id']},
                    {"$set": {"slack_channel_id": slack_channel_id}}
                )

                # Send a welcome message to the user in the channel
                welcome_message = "Welcome to our Slack channel! We are excited to have you here."
                slack_user_client.chat_postEphemeral(channel=slack_channel_id, text=welcome_message,
                                                     user=slack_user_id)
            except slack.errors.SlackApiError as e:
                if 'channel_already_exists' in str(e):
                    print("Private channel already exists.")
                else:
                    print(f"Error creating channel: {e}")
        else:
            print("Slack channel ID already exists for this channel.")

    except Exception as e:
        print(f"Error in add_slack_channel: {e}")


def list_channels_for_user(db, user_email):
    try:
        users_collection = db['users']
        user = users_collection.find_one({"user_email": user_email})
        company_id = user['company_id']
        collection = db['channels']

        # Query to find all documents with the specified company_name
        query = {'company_id': company_id}
        channels = collection.find(query)
        return channels
    except Exception as e:
        print(f'Failed to list channels for user : {user_email}')
        print(e)


def connect_to_mongodb():
    try:
        MONGODB_URI = ("mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w"
                       "=majority&appName=Cluster0");
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        print("Connected successfully to MongoDB")
        return db
    except Exception as e:
        print("Failed to connect to MongoDB")
        print(e)


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
        return '[]'  # Return empty JSON array in case of error


def get_token(code):
    try:
        url = "https://oauth2.googleapis.com/token"
        logger.info(f'code: {code}')
        logger.info(f'client_id: {os.getenv("GOOGLE_CLIENT_ID")}')
        logger.info(f'client_secret: {os.getenv("GOOGLE_CLIENT_SECRET")}')
        params = {
            "code": code,
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "redirect_uri": "http://localhost:8080/usable/folder_path"
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
        raise e


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
