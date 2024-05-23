import os

import psycopg2
from itsdangerous import URLSafeTimedSerializer
from pinecone import Pinecone
from pymongo import MongoClient


# Function to connect to MongoDB
def connect_to_mongodb():
    try:
        MONGODB_URI = "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        print("Connected successfully to MongoDB")
        return db
    except Exception as e:
        print("Failed to connect to MongoDB")
        print(e)


def get_company_id(db, user_id):
    try:
        collection = db['users']
        user = collection.find_one({"userId": user_id})
        if user:
            return user.get("companyId")
        else:
            return None
    except Exception as e:
        print(f'Failed to get company id for user: {user_id}')
        print(e)


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


def delete_records_from_postgres(CONNECTION_STRING, custom_ids):
    db_params = {
        "host": "104.154.107.148",
        "port": "5432",
        "database": "docstore",
        "user": "postgres",
        "password": "casperAI"
    }
    try:
        # Connect to the PostgreSQL database
        connection = psycopg2.connect(**db_params)

        # Create a cursor object
        cursor = connection.cursor()

        # Create the DELETE query
        delete_query = "DELETE FROM langchain_storage_items WHERE custom_id = ANY(%s)"

        # Execute the DELETE query for the array of custom_ids
        cursor.execute(delete_query, (custom_ids,))

        # Commit the transaction
        connection.commit()

        # Close the cursor and connection
        cursor.close()
        connection.close()

        print("Records deleted successfully")

    except (Exception, psycopg2.Error) as error:
        print("Error while deleting records from PostgreSQL:", error)


def delete_file(user_id, file_id):
    db = connect_to_mongodb()
    company_id = get_company_id(db, user_id)
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(company_id)
    records = query_records_by_metadata(index, 'file_id', file_id)
    # Extract IDs from the query result
    record_ids = [record['id'] for record in records]
    doc_ids = [record['metadata']['doc_id'] for record in records]
    CONNECTION_STRING = "postgresql+psycopg2://postgres:casperAI@104.154.107.148:5432/docstore"
    delete_records_from_postgres(CONNECTION_STRING, doc_ids)
    # Delete the records
    delete_records_from_vectordb(index, record_ids)


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


def get_shared_users(user_id):
    db = connect_to_mongodb()
    company_id = get_company_id(db, user_id)
    collection = db['users']
    users = collection.find({"companyId": company_id})
    # Extract user IDs from the query result
    user_ids = [user['userId'] for user in users]
    return user_ids
