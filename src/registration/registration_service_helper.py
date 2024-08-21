from datetime import datetime

from bson import ObjectId
from pymongo import MongoClient


def add_users(db, user_emails, company_id):
    try:
        collection = db['users']
        for user_email in user_emails:
            if collection.find_one({'user_email': user_email}) is None:
                document = {
                    'user_email': user_email,
                    'company_id': company_id,
                    'is_verified': False,
                    'slack_app_opened': False
                }
                insert_result = collection.insert_one(document)
            else:
                print(f'User already exists: {user_email}')
    except Exception as e:
        print(f'Failed to insert user : {user_email}')
        print(e)


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


def persist_company_info(db, name, address, city, state, phone_number, admin_email):
    try:
        collection = db['companies']
        document = {
            'name': name,
            'address': address,
            'city': city,
            'state': state,
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


def persist_channel_info(db, channel_name, company_id, admin_email):
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


def list_channel_names(db, user_email):
    try:
        users_collection = db['users']
        user = users_collection.find_one({"user_email": user_email})
        company_id = user['company_id']
        collection = db['channels']

        # Query to find all documents with the specified company_name
        query = {'company_id': company_id}
        channels = collection.find(query)

        # Extract and print all channel_name values
        channel_names = [channel['channel_name'] for channel in channels]
        return channel_names
    except Exception as e:
        print(f'Failed to list channels for user : {user_email}')
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
