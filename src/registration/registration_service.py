from bson import ObjectId
from flask import Flask, request, jsonify, abort, make_response
from flask_cors import CORS

from registration_service_helper import connect_to_mongodb, persist_company_info, add_users, get_company_for_user, \
    persist_channel_info, list_channel_names, get_documents_by_channel

app = Flask(__name__)
CORS(app)


@app.route('/company-registration', methods=['POST'])
def register_company():
    # Get data from request
    data = request.get_json()

    # Extract parameters
    name = data.get('company')
    address = data.get('address')
    city = data.get('city')
    state = data.get('state')
    country = data.get('country')
    phone_number = data.get('phone_number')
    admin_email = data.get('admin_email')
    db = connect_to_mongodb()
    collection = db['companies']
    # Check if a document with the same name and admin_email already exists
    existing_document = collection.find_one({'name': name, 'admin_email': admin_email})
    if existing_document is None:
        company_id = persist_company_info(db, name, address, city, state, phone_number, admin_email)
        add_users(db, [admin_email], company_id)

        data = {
            'success': True,
            'message': 'Company registered successfully',
            'company_id': company_id
        }
        response = jsonify(data)
        response.headers.add('Access-Control-Allow-Origin', '*')
    else:
        # Document with the same name and admin_email already exists
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
    # Get data from request
    data = request.get_json()

    # Extract parameters
    channel_name = data.get('channel_name')
    admin_email = data.get('admin_email')

    db = connect_to_mongodb()
    company_info = get_company_for_user(db, admin_email)
    company_id = str(company_info['_id']) if '_id' in company_info and isinstance(company_info['_id'],
                                                                                  ObjectId) else None

    if not company_id or not channel_name or not admin_email:
        return jsonify({"error": "company_id, channel_name, and admin_email are required"}), 400
    collection = db['channels']
    existing_document = collection.find_one({'channel_name': channel_name, 'admin_email': admin_email, 'company_id': company_id})
    if existing_document is None:
        generated_id = persist_channel_info(db, channel_name, company_id, admin_email)

        if generated_id:
            response_data = {
                'success': True,
                'message': 'Channel added successfully',
                'id': str(generated_id)
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
    channel_names = list_channel_names(db, user_email)
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
    if user:
        response = jsonify({
            "success": True,
            "user_id": str(user['_id']),
            "user_email": user['user_email'],
            "company_id": user['company_id'],
            "is_verified": user['is_verified']
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
