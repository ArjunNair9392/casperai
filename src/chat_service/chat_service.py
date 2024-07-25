from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from PIL import Image
from flask import request, Flask, jsonify, Response
from langchain_community.vectorstores import Pinecone as lc_pinecone
from langchain_openai import OpenAIEmbeddings
from langchain.retrievers.multi_vector import MultiVectorRetriever
from pinecone import PodSpec, Pinecone
from langchain_community.storage import SQLDocStore
from typing import List
from langchain_core.retrievers import BaseRetriever, Document
from slackeventsapi import SlackEventAdapter
from slack_bolt import App
from slack_sdk import WebClient
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk.web import SlackResponse
from dotenv import load_dotenv

import io
import re
import base64
import pandas as pd
from pymongo import MongoClient
import os
import flask
import slack

app = Flask(__name__)

load_dotenv()
# Initialize the app with your bot token and signing secret
slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Create a request handler
handler = SlackRequestHandler(slack_app)


@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


# Event listener for app installation
@slack_app.event("app_home_opened")
def handle_channel_creation(event, say):
    # Get the user ID of the installer
    user_id = event["user"]
    slack_bot_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    welcome_message = "Welcome to Casper AI! We will now create 4 private channels for you and please add users!"
    slack_bot_client.chat_postMessage(channel=user_id, text=welcome_message)
    slack_client = WebClient(token=os.getenv("SLACK_USER_TOKEN"))
    welcome_message = "Welcome to Casper AI! We will now create 4 private channels for you and please add users!"
    slack_client.chat_postMessage(channel=user_id, text=welcome_message)
    try:
        # Create a private channel
        response = slack_client.conversations_create(
            name="test9",
            is_private=True
        )

        channel_id = response["channel"]["id"]

        # Get the bot user ID
        auth_response = slack_bot_client.auth_test()
        bot_user_id = auth_response['user_id']

        # Invite the bot to the private channel
        invite_response = slack_client.conversations_invite(
            channel=channel_id,
            users=bot_user_id
        )

        # Send a welcome message in the channel
        welcome_message = "Welcome to our Slack workspace! We are excited to have you here."
        slack_client.chat_postMessage(channel=channel_id, text=welcome_message)
    except slack.errors.SlackApiError as e:
        if 'channel_already_exists' in str(e):
            print("Private channel already exists")
        else:
            print(f"Error creating channel: {e}")


@app.route('/ask-casper', methods=['POST'])
def test_call():
    slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    data = request.form
    user_id = data.get('user_id')
    channel_id = data.get('channel_id')
    print(data)
    print("channel_id: ",channel_id)
    text = data.get('text')

    response_url = data.get('response_url')

    # Respond to the user with an ephemeral message
    response_message = f"You said: {text}"

    user_info = slack_client.users_info(user=user_id)
    email = user_info['user']['profile']['email']

    slack_response = slack_client.chat_postEphemeral(
        channel=channel_id,
        text=response_message,
        user=user_id
    )

    return Response(), 200


def looks_like_base64(sb):
    if not isinstance(sb, str):
        return False
    return re.match("^[A-Za-z0-9+/]+[=]{0,2}$", sb) is not None


def is_image_data(b64data):
    """
    Check if the base64 data is an image by looking at the start of the data
    """
    image_signatures = {
        b"\xFF\xD8\xFF": "jpg",
        b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A": "png",
        b"\x47\x49\x46\x38": "gif",
        b"\x52\x49\x46\x46": "webp",
    }
    try:
        header = base64.b64decode(b64data)[:8]  # Decode and get the first 8 bytes
        for sig, format in image_signatures.items():
            if header.startswith(sig):
                return True
        return False
    except Exception:
        return False


def resize_base64_image(base64_string, size=(128, 128)):
    """
    Resize an image encoded as a Base64 string
    """
    # Decode the Base64 string
    img_data = base64.b64decode(base64_string)
    img = Image.open(io.BytesIO(img_data))

    # Resize the image
    resized_img = img.resize(size, Image.LANCZOS)

    # Save the resized image to a bytes buffer
    buffered = io.BytesIO()
    resized_img.save(buffered, format=img.format)

    # Encode the resized image to Base64
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def split_image_text_types(docs):
    """
    Split base64-encoded images and texts
    """
    b64_images = []
    texts = []
    table_df = []
    for doc in docs:
        # Check if the document is of type Document and extract page_content if so
        if isinstance(doc, Document):
            doc = doc.page_content
        if isinstance(doc, pd.DataFrame):
            table_df.append(doc)
        elif looks_like_base64(doc) and is_image_data(doc):
            doc = resize_base64_image(doc, size=(1300, 600))
            b64_images.append(doc)
        else:
            texts.append(doc)
    return {"images": b64_images, "texts": texts, "tables": table_df}


def img_prompt_func(data_dict):
    """
    Join the context into a single string
    """

    formatted_texts = "\n".join([str(elem) for sublist in data_dict["context"]["texts"] for elem in sublist])
    messages = []

    # Adding table(s) to the messages if present
    table_message = ""
    if data_dict["context"]["tables"]:
        for table in data_dict["context"]["tables"]:
            df = pd.DataFrame(table)
            table_message += str(df)
            table_message += "\n"  # add a newline between tables

    # Append table messages to formatted_texts
    if table_message:
        formatted_texts += "\nTables:\n" + table_message

    # Adding image(s) to the messages if present
    if data_dict["context"]["images"]:
        for image in data_dict["context"]["images"]:
            image_message = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            }
            messages.append(image_message)

    # Adding the text for analysis
    text_message = {
        "type": "text",
        "text": (
            "You are a helpful chat bot.\n"
            "You will be given a mixed of text, tables, and image(s).\n"
            "Use this information to answer the user question. \n"
            "Only limit your knowledge to context set here. \n"
            f"User-provided question: {data_dict['question']}\n\n"
            "Text and / or tables context:\n"
            f"{formatted_texts}"
        ),
    }
    messages.append(text_message)
    return [HumanMessage(content=messages)]


def multi_modal_rag_chain(retriever):
    """
    Multi-modal RAG chain
    """
    # Multi-modal LLM
    model = ChatOpenAI(temperature=0, model="gpt-4-vision-preview", openai_api_key=os.getenv("OPENAI_API_KEY"))

    # RAG pipeline
    chain = (
            {
                "context": retriever | RunnableLambda(split_image_text_types),
                "question": RunnablePassthrough(),
            }
            | RunnableLambda(img_prompt_func)
            | model
            | StrOutputParser()
    )

    return chain


def fetchIndexName(user_id, channel_name):
    MONGODB_URI = "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
    try:
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        print("Connected successfully")
        user_collection = db['users']  # Use your collection name here

        user_data = user_collection.find_one({'userId': user_id})
        company_id = user_data['companyId']
        index_name = get_channel_id_by_name_and_company(db, channel_name, company_id)
        return index_name
    except Exception as e:
        print("Failed to connect to MongoDB")
        print(e)

def get_channel_id_by_name_and_company(db, channel_name, company_name):
    try:
        collection = db['channels']
        document = collection.find_one({
            'channel_name': channel_name,
            'company_name': company_name
        }, {'_id': 1})  # Only retrieve the _id field
        if document:
            return document.get('_id')
        else:
            return None
    except Exception as e:
        print(f'Failed to get channel id for channel: {channel_name} and company: {company_name}')
        print(e)
        return None


def get_vectorestore(indexName):
    # pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    # pinecone.deinitialize()

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index_name = indexName
    indexes = pc.list_indexes().names()
    if index_name in indexes:
        print("Pinecode index found")
        index = pc.Index(index_name)
    else:
        # Create the index in case it doesn't exist
        print("Pinecode index not found, creating one")
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric="euclidean",
            spec=PodSpec(environment=os.getenv("PINECONE_API_ENV"))
        )
        index = pc.Index(index_name)

    #OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

    # model_name = 'text-embedding-ada-002'
    model_name = 'text-embedding-3-small'

    embed = OpenAIEmbeddings(
        model=model_name,
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    # Instantiate Pinecone vectorstore
    vectorstore = lc_pinecone(index, embed, "text")

    return vectorstore


def getRetriever(indexName):
    vectorstore = get_vectorestore(indexName)
    COLLECTION_NAME = indexName

    docstore = SQLDocStore(
        collection_name=COLLECTION_NAME,
        connection_string=os.getenv("POSTGRES_CONNECTION_STRING"),
    )
    print("Connection to PostgreSQL DB successful")
    id_key = "doc_id"

    # Create the multi-vector retriever
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        id_key=id_key,
    )

    return retriever


@app.route('/chat', methods=['POST'])
def chat():
    data = flask.request.get_json()
    userId = data.get('userId')
    channel_id = data.get('channel_name')
    query = data.get('query')
    indexName = fetchIndexName(userId, channel_id)
    retriever = getRetriever(indexName)
    vectorstore = get_vectorestore(indexName)
    last_item = query[-1]
    # Extract and remove the last element with role="user" as question
    if last_item['role'] == 'user':
        question = last_item['content']
        query.pop()  # Remove the last item from the list
    else:
        question = None
    history = query
    # Combine the current question with the history to provide context
    full_query = f"{question} {history}"
    # Directly call the vectorstore and get all relevant documents. similarity_search
    # called internally by get_relevant_documents.
    relevant_documents = vectorstore.similarity_search(full_query, k=3)
    # Get file_id for each document
    # TODO: Will be used to cite source.
    for doc in relevant_documents:
        file_id = doc.metadata['file_id']
    history_aware_retriever = lambda query: (retriever.get_relevant_documents(full_query, limit=3), history)
    chain_multimodal_rag = multi_modal_rag_chain(history_aware_retriever)
    response = chain_multimodal_rag.invoke({
        "question": question,
        "history": history
    })
    return jsonify(response)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
