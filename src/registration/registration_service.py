import os
from bson import ObjectId
from flask import Flask, request, jsonify, abort, make_response
from flask_cors import CORS
from dotenv import load_dotenv
from slack_sdk import WebClient

from logging_config import logger
from registration_service_helper import connect_to_mongodb, persist_company_info, get_company_for_user, \
    persist_channel_info, list_channels_for_user, get_documents_by_channel, get_token, persist_token, fetch_token, \
    add_slack_channel

app = Flask(__name__)
CORS(app)
load_dotenv()


@app.route('/company-registration', methods=['POST'])
def register_company():
    data = request.get_json()
    name = data.get('company')
    address = data.get('address')
    city = data.get('city')
    state = data.get('state')
    country = data.get('country')
    phone_number = data.get('phone_number')
    admin_email = data.get('admin_email')
    db = connect_to_mongodb()
    collection = db['companies']
    existing_document = collection.find_one({'name': name, 'admin_email': admin_email})
    if existing_document is None:
        company_id = persist_company_info(db, name, address, city, state, country, phone_number, admin_email)
        users_collection = db['users']
        user = users_collection.find_one({"user_email": admin_email})
        if user:
            users_collection.update_one(
                {"user_email": admin_email},
                {"$set": {"company_id": company_id}}
            )

        data = {
            'success': True,
            'message': 'Company registered successfully',
            'company_id': company_id
        }
        response = jsonify(data)
        response.headers.add('Access-Control-Allow-Origin', '*')
    else:
        print(f'Company info for {name} with admin_email {admin_email} already exists.')
        company_id = str(existing_document['_id'])
        data = {
            'success': False,
            'message': 'Company was already registered with same name and admin email',
            'company_id': company_id
        }
        response = jsonify(data)
    return response, 200


@app.route('/add-channel', methods=['POST'])
def add_channel():
    data = request.get_json()
    channel_name = data.get('channel_name')
    admin_email = data.get('admin_email')
    slack_workspace = data.get('slack_workspace')

    slack_bot_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    db = connect_to_mongodb()
    company_info = get_company_for_user(db, admin_email)
    company_id = str(company_info['_id']) if '_id' in company_info and isinstance(company_info['_id'],
                                                                                  ObjectId) else None

    if not company_id or not channel_name or not admin_email:
        return jsonify({"error": "company_id, channel_name, and admin_email are required"}), 400
    channel_collection = db['channels']
    users_collection = db['users']
    user = users_collection.find_one({"user_email": admin_email})
    existing_document = channel_collection.find_one(
        {'channel_name': channel_name, 'admin_email': admin_email, 'company_id': company_id})
    if existing_document is None:
        channel = persist_channel_info(db, channel_name, company_id, admin_email, slack_workspace)
        welcome_message = f"Welcome to CasperAI. We have created some channels for you!"
        slack_bot_client.chat_postEphemeral(channel=user['slack_user_id'], text=welcome_message, user=user['slack_user_id'])
        if channel.inserted_id:
            response_data = {
                'success': True,
                'message': 'Channel added successfully',
                'id': str(channel.inserted_id)
            }
        else:
            response_data = {
                'success': False,
                'message': 'Failed to add channel'
            }
        response = jsonify(response_data)
    else:
        response_data = {
            'success': False,
            'message': f'Channel with the same name exists under this company! Company ID: {company_id}',
            'id': str(existing_document['_id'])
        }
        response = jsonify(response_data)

    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


@app.route('/list-channels-for-user', methods=['GET'])
def get_channels_for_user():
    user_email = request.args.get('user_email')
    db = connect_to_mongodb()
    channels = list_channels_for_user(db, user_email)
    channel_names = [channel['channel_name'] for channel in channels]
    if channel_names:
        response = jsonify({"success": True, "channel_names": channel_names})
    else:
        response = jsonify({"success": False, "channel_names": []})
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


@app.route('/get-user', methods=['GET'])
def get_user():
    user_email = request.args.get('user_email')
    db = connect_to_mongodb()
    users_collection = db['users']
    user = users_collection.find_one({"user_email": user_email})
    token_result = fetch_token(db, user_email)
    does_token_exist = False
    if token_result:
        does_token_exist = True
    if user:
        response = jsonify({
            "success": True,
            "user_id": str(user['_id']),
            "user_email": user['user_email'],
            'slack_user_id': user['slack_user_id'],
            'slack_workspace': user['slack_workspace'],
            "company_id": user['company_id'],
            "is_verified": user['is_verified'],
            "does_token_exist": does_token_exist
        })
    else:
        response = jsonify({"success": False, "message": "User not found"})
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


@app.route('/list-files-from-channel', methods=['GET'])
def list_files_for_channel():
    try:
        user_email = request.args.get('user_email')
        channel_name = request.args.get('channel_name')

        db = connect_to_mongodb()
        users_collection = db['users']

        # Check if the user exists
        user = users_collection.find_one({"user_email": user_email})
        if not user:
            data = {
                'success': False,
                'message': 'User not found with the given email.'
            }
            response = jsonify(data)
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response, 200

        # Check if the company_id is present in the user's document
        company_id = user.get('company_id')
        if not company_id:
            data = {
                'success': False,
                'message': 'Company ID not found for the user.'
            }
            response = jsonify(data)
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response, 200

        channels_collection = db['channels']

        # Check if the channel exists for the given company_id
        channel = channels_collection.find_one({
            'channel_name': channel_name,
            'company_id': company_id
        }, {'_id': 1})  # Only retrieve the _id field

        if not channel:
            data = {
                'success': False,
                'message': 'Wrong channel name for the given company.'
            }
            response = jsonify(data)
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response, 200

        # If everything is valid, get the documents by channel
        data = get_documents_by_channel(db, str(channel['_id']))
        jsonData = jsonify({"success": True, "files": data})
        response = make_response(jsonData)
        response.headers.add('Content-Type', 'application/json')
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 200
    except Exception as e:
        # Optionally, you can log the error or take other appropriate actions
        data = {
            'error': 'An error occurred during file processing'
        }
        response = jsonify(data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500


@app.route('/connect-gdrive', methods=['POST'])
def connect_gdrive():
    # Get data from request
    data = request.get_json()
    # Extract parameters
    user_email = data.get('user_email')
    code = data.get('code')
    db = connect_to_mongodb()
    try:
        logger.info(f'fetching token from google api for user: {user_email}')
        token_result = get_token(code)
        token = token_result.get("access_token")
        refresh_token = token_result.get("refresh_token")
        persist_token(db, user_email, token, refresh_token)
        response_data = {
            'success': True,
            'message': 'connected to google drive successfully'
        }
    except Exception as e:
        logger.info(f'Failed to fetch token for user: {user_email}')
        response_data = {
            'success': False,
            'message': 'Failed to connect with google drive'
        }
        response = jsonify(response_data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500
    response = jsonify(response_data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
