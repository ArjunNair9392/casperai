import os
import uuid

from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from logging_config import logger
from pinecone import Pinecone, ServerlessSpec

# Local Python files
from docstore.sqlalchemy_docstore import SQLAlchemyDocStore


def get_vectorestore(indexName):
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index_name = indexName
    indexes = pc.list_indexes().names()
    logger.info("Indexes: ")
    logger.info(indexes)
    if index_name in indexes:
        logger.info("Pinecone index found")
        index = pc.Index(index_name)
    else:
        # Create the index in case it doesn't exist
        logger.info("Pinecone index not found, creating one")
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric="euclidean",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        index = pc.Index(index_name)

    model_name = 'text-embedding-3-small'

    embed = OpenAIEmbeddings(
        model=model_name,
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    # Instantiate Pinecone vectorstore
    vectorstore = PineconeVectorStore(index_name=index_name, embedding=embed)

    return vectorstore


def create_multi_vector_retriever(
        text_summaries, texts, table_summaries, tables, image_summaries, images, index_name, file_id
):
    """
    Create retriever that indexes summaries, but returns raw images or texts
    """
    # Pinecone vectorstore
    vectorstore = get_vectorestore(index_name)
    COLLECTION_NAME = index_name

    postgres_docstore = SQLAlchemyDocStore(db_url=os.getenv("POSTGRES_CONNECTION_STRING"), namespace=COLLECTION_NAME)

    logger.info("Connection to Postgres DB successful")
    id_key = "doc_id"

    # Create the multi-vector retriever
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=postgres_docstore,
        id_key=id_key,
    )

    # Helper function to add documents to the vectorstore and docstore
    def add_documents(local_retriever, doc_summaries, doc_contents, local_file_id):
        doc_ids = [str(uuid.uuid4()) for _ in doc_contents]
        documents = [
            (doc_ids[i], doc_contents[i], {"file_id": file_id})
            for i in range(len(doc_contents))
        ]
        summary_docs = [
            Document(page_content=s, metadata={id_key: doc_ids[i], "file_id": local_file_id})
            for i, s in enumerate(doc_summaries)
        ]
        local_retriever.vectorstore.add_documents(summary_docs)
        local_retriever.docstore.mset(documents)

    # Add texts, tables, and images
    # Check that text_summaries is not empty before adding
    if text_summaries:
        add_documents(retriever, text_summaries, texts, file_id)
    # Check that table_summaries is not empty before adding
    if table_summaries:
        add_documents(retriever, table_summaries, tables, file_id)
    # Check that image_summaries is not empty before adding
    if image_summaries:
        add_documents(retriever, image_summaries, images, file_id)

    return retriever
