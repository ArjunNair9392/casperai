from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from bson import ObjectId

from utility_functions import connect_to_mongodb, persist_company_info, add_users, get_company_for_user, \
    persist_channel_info, list_channel_names

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
    company_info = get_company_for_user(db, admin_email)
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


@app.route('/list-channels-for-user', methods=['GET'])
def get_channels_for_user():
    user_email = request.args.get('user_email')
    db = connect_to_mongodb()
    channel_names = list_channel_names(db, user_email)
    if channel_names:
        response = jsonify({"channel_names": channel_names})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    else:
        abort(404)


# TODO: Ask Amit if this is still needed
@app.route('/get-admin-info', methods=['GET'])
def get_company():
    admin_email = request.args.get('adminEmail')
    db = connect_to_mongodb()
    result = get_company_for_user(db, admin_email)
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
    user_emails = data.get('user_emails', [])
    company = data.get('company_id')

    db = connect_to_mongodb()
    add_users(db, user_emails, company)
    data = {
        'status': 'SUCCESS',
    }
    response = jsonify(data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
