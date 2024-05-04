from flask import Flask, request, jsonify, abort
from pymongo import MongoClient

app = Flask(__name__)

@app.route('/companyRegistration', methods=['POST'])
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

    response = {
        'status': 'success',
        'message': 'Company registered successfully'
    }

    return jsonify(response),200
@app.route('/getAdminInfo', methods=['GET'])
def get_company():
    admin_email = request.args.get('adminEmail')
    db = connect_to_mongodb()
    result = get_company_for_admin(db, admin_email)
    if result:
        name = result.get("name")
        admin_email = result.get("admin_email")
        return jsonify({"company" : name,
                        "admin_email" : admin_email})
    else:
        abort(404)

@app.route('/addUsers', methods=['POST'])
def add_users_to_company():
    # Get list of user email IDs from request JSON
    data = request.get_json()
    userIds = data.get('userIds', [])
    company = data.get('company')

    db = connect_to_mongodb()
    add_users(db, userIds, company)
    response = {
        'status': 'success',
    }

    return jsonify(response), 200

def add_users(db, userIds, company):
    try:
        collection = db['users']
        for userId in userIds:
            document = {
                'userId': userId,
                'companyId': company
            }
            insert_result = collection.insert_one(document)
            print(f'Inserted user : {userId}')
    except Exception as e:
        print(f'Failed to insert user : {userId}')
        print(e)
def get_company_for_admin(db, admin_email):
    try:
        collection = db['companies']

        # Define a document to be inserted
        query = {"admin_email": admin_email}
        projection = {"admin_email", "name"}   # You can specify fields to include or exclude in the result
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
def connect_to_mongodb():
    try:
        MONGODB_URI =  "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        print("Connected successfully to MongoDB")
        return db
    except Exception as e:
        print("Failed to connect to MongoDB")
        print(e)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
