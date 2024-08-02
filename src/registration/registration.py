from flask import Flask, request, jsonify, abort
from pymongo import MongoClient
from flask_cors import CORS
from bson import ObjectId
from datetime import datetime

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
    persist_company_info(db, name, address, city, state, phone_number, admin_email)
    add_users(db, [admin_email], name)

    data = {
        'status': 'success',
        'message': 'Company registered successfully'
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response, 200


@app.route('/add-channel', methods=['POST'])
def add_channel():
    # Get data from request
    data = request.get_json()

    # Extract parameters
    channel_name = data.get('channel_name')
    admin_email = data.get('admin_email')

    db = connect_to_mongodb()
    company_info = get_company_for_admin(db, admin_email)
    company_id = str(company_info['_id']) if '_id' in company_info and isinstance(company_info['_id'],
                                                                                  ObjectId) else None

    if not company_id or not channel_name or not admin_email:
        return jsonify({"error": "company_id, channel_name, and admin_email are required"}), 400

    db = connect_to_mongodb()
    generated_id = persist_channel_info(db, channel_name, company_id, admin_email)

    if generated_id:
        response_data = {
            'status': 'success',
            'message': 'Channel added successfully',
            'id': str(generated_id)
        }
    else:
        response_data = {
            'status': 'failure',
            'message': 'Failed to add channel'
        }

    response = jsonify(response_data)
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response, 200 if generated_id else 500


@app.route('/list-channels-for-company', methods=['GET'])
def get_channels_by_company():
    company_name = request.args.get('company_name')
    db = connect_to_mongodb()
    channel_names = list_channel_names(db, company_name)
    if channel_names:
        response = jsonify({"channel_names": channel_names})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    else:
        abort(404)


@app.route('/get-admin-info', methods=['GET'])
def get_company():
    admin_email = request.args.get('adminEmail')
    db = connect_to_mongodb()
    result = get_company_for_admin(db, admin_email)
    if result:
        name = result.get("name")
        admin_email = result.get("admin_email")
        data = {
            "company": name,
            "admin_email": admin_email
        }
        response = jsonify(data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    else:
        abort(404)


@app.route('/add-users', methods=['POST'])
def add_users_to_company():
    # Get list of user email IDs from request JSON
    data = request.get_json()
    userIds = data.get('userIds', [])
    company = data.get('company')

    db = connect_to_mongodb()
    add_users(db, userIds, company)
    data = {
        'status': 'success',
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


def add_users(db, userIds, company):
    try:
        collection = db['users']
        for userId in userIds:
            if collection.find_one({'userId': userId}) is None:
                document = {
                    'userId': userId,
                    'companyId': company,
                    'isVerified': False  # type: ignore
                }
                insert_result = collection.insert_one(document)
                print(f'Inserted user : {userId}')
            else:
                print(f'User already exists: {userId}')
    except Exception as e:
        print(f'Failed to insert user : {userId}')
        print(e)


def get_company_for_admin(db, admin_email):
    try:
        collection = db['companies']

        # Define a document to be inserted
        query = {"admin_email": admin_email}
        projection = {"admin_email", "name"}  # You can specify fields to include or exclude in the result
        result = collection.find_one(query, projection)
        if result:
            print(f'Company for admin: {result.get("admin_email")}')
            return result
        else:
            print(f'Company not found for admin: {admin_email}')
    except Exception as e:
        print(f'Failed to fetch company not found for admin: {admin_email}')
        print(e)
    return result


def persist_company_info(db, name, address, city, state, phone_number, admin_email):
    try:
        collection = db['companies']
        document = {
            'name': name,
            'address': address,
            'city': city,
            'state': state,
            'phone_number': phone_number,
            'admin_email': admin_email
        }
        insert_result = collection.insert_one(document)
        print(f'Inserted company info for : {name}')
    except Exception as e:
        print(f'Failed to insert company info for : {name}')
        print(e)


def persist_channel_info(db, channel_name, company_id, admin_email):
    try:
        collection = db['channels']
        existing_document = collection.find_one({'channel_name': channel_name, 'company_id': company_id})
        if not existing_document:
            document = {
                'channel_name': channel_name,
                'company_id': company_id,
                'admin_email': admin_email,
                'member_ids': [],
                'timestamp': datetime.now(),
            }
            insert_result = collection.insert_one(document)
            generated_id = insert_result.inserted_id
            print(f'Inserted channel info for: {channel_name}, {company_id}')
            return generated_id
        else:
            return existing_document['_id']
    except Exception as e:
        print(f'Failed to insert channel info for: {channel_name}, {company_id}')
        print(e)
        return None


def list_channel_names(db, company_name):
    try:
        collection = db['channels']

        # Query to find all documents with the specified company_name
        query = {'company_name': company_name}
        documents = collection.find(query)

        # Extract and print all channel_name values
        channel_names = [doc['channel_name'] for doc in documents]
        return channel_names
    except Exception as e:
        print(f'Failed to list channels for company : {company_name}')
        print(e)


def connect_to_mongodb():
    try:
        MONGODB_URI = "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        print("Connected successfully to MongoDB")
        return db
    except Exception as e:
        print("Failed to connect to MongoDB")
        print(e)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
