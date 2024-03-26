from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain_core.documents import Document
from langchain.storage import InMemoryStore
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Pinecone as lc_pinecone
from pinecone import PodSpec, Pinecone
from langchain_community.storage import SQLDocStore

import uuid
import os


def get_vectorestore(indexName):
    pc = Pinecone( api_key=os.getenv("PINECONE_API_KEY") )
    index_name = indexName
    indexes = pc.list_indexes().names()
    print("Indexes: ")
    print(indexes)
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

    model_name = 'text-embedding-ada-002'

    embed = OpenAIEmbeddings(
        model=model_name,
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    # Instantiate Pinecone vectorstore
    vectorstore = lc_pinecone(index, embed.embed_query, "text")

    return vectorstore

def create_multi_vector_retriever(
    text_summaries, texts, table_summaries, tables, image_summaries, images, indexName
):
    """
    Create retriever that indexes summaries, but returns raw images or texts
    """
    # Pinecode vectorstore
    vectorstore = get_vectorestore(indexName)

    # CONNECTION_STRING = "postgresql+psycopg2://localhost:5432/db"
    # #   To start postgresql@14 now and restart at login:
    # #       brew services start postgresql@14
    # #   Or, if you don't want/need a background service you can just run:
    # #       /opt/homebrew/opt/postgresql@14/bin/postgres -D /opt/homebrew/var/postgresql@14
    # COLLECTION_NAME = "casperai"
    # docstore = SQLDocStore(
    #     collection_name=COLLECTION_NAME,
    #     connection_string=CONNECTION_STRING,
    # )

    CONNECTION_STRING = "postgresql+psycopg2://postgres:test@localhost:5432/mydatabase"
    COLLECTION_NAME = indexName

    docstore = SQLDocStore(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
    )
    print("Connection to PostgreSQL DB successful")
    id_key = "doc_id"
    #store = InMemoryStore()

    # Create the multi-vector retriever
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        id_key=id_key,
    )

    # Helper function to add documents to the vectorstore and docstore
    def add_documents(retriever, doc_summaries, doc_contents):
        doc_ids = [str(uuid.uuid4()) for _ in doc_contents]
        summary_docs = [
            Document(page_content=s, metadata={id_key: doc_ids[i]})
            for i, s in enumerate(doc_summaries)
        ]
        retriever.vectorstore.add_documents(summary_docs)
        retriever.docstore.mset(list(zip(doc_ids, doc_contents)))

    # Add texts, tables, and images
    # Check that text_summaries is not empty before adding
    if text_summaries:
        add_documents(retriever, text_summaries, texts)
    # Check that table_summaries is not empty before adding
    if table_summaries:
        add_documents(retriever, table_summaries, tables)
    # Check that image_summaries is not empty before adding
    if image_summaries:
        add_documents(retriever, image_summaries, images)

    return retriever