from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from PIL import Image
import flask
from flask import request, Flask, jsonify
from langchain_community.vectorstores import Pinecone as lc_pinecone
from langchain_openai import OpenAIEmbeddings
from langchain.retrievers.multi_vector import MultiVectorRetriever
from pinecone import PodSpec, Pinecone
from langchain_community.storage import SQLDocStore

import io
import re
import base64
import pandas as pd
from pymongo import MongoClient
import os

app = Flask(__name__)
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
    model = ChatOpenAI(temperature=0, model="gpt-4-vision-preview", max_tokens=1024, openai_api_key=os.getenv("OPENAI_API_KEY"))

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


def fetchIndexName(user_id):
    MONGODB_URI = "mongodb+srv://casperai:Xaw6K5IL9rMbcsVG@cluster0.25foikp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";
    try:
        client = MongoClient(MONGODB_URI)
        db = client['Casperai']
        print("Connected successfully")
        user_collection = db['users']  # Use your collection name here

        user_data = user_collection.find_one({'userId': user_id})
        return user_data['companyId']
    except Exception as e:
        print("Failed to connect to MongoDB")
        print(e)

def get_vectorestore(indexName):
    # pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    # pinecone.deinitialize()

    pc = Pinecone( api_key=os.getenv("PINECONE_API_KEY") )
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

    model_name = 'text-embedding-ada-002'

    embed = OpenAIEmbeddings(
        model=model_name,
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    # Instantiate Pinecone vectorstore
    vectorstore = lc_pinecone(index, embed.embed_query, "text")

    return vectorstore
def getRetriever(indexName):
    vectorstore = get_vectorestore(indexName)

    CONNECTION_STRING = "postgresql+psycopg2://postgres:casperAI@104.154.107.148:5432/docstore"
    COLLECTION_NAME = indexName

    docstore = SQLDocStore(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
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
    query = data.get('query')
    indexName = fetchIndexName(userId)
    retriever = getRetriever(indexName)
    last_item = query[-1]
    # Extract and remove the last element with role="user" as question
    if last_item['role'] == 'user':
        question = last_item['content']
        query.pop()  # Remove the last item from the list
    else:
        question = None

    history = query
    history_aware_retriever = lambda query: (retriever.get_relevant_documents(question), history)
    chain_multimodal_rag = multi_modal_rag_chain(history_aware_retriever)
    response = chain_multimodal_rag.invoke({
        'question' : question
    })
    return jsonify(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)