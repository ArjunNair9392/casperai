from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain_core.documents import Document
from langchain.storage import InMemoryStore
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Pinecone as lc_pinecone
from pinecone import PodSpec, Pinecone
from langchain_community.storage import SQLDocStore

import uuid
import os

def get_pinecone_index(index_name):
    """
    Get or create the Pinecone vector index.
    """
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    indexes = pc.list_indexes().names()
    
    if index_name in indexes:
        print(f"Pinecone index '{index_name}' found")
        return pc.Index(index_name)
    else:
        print(f"Pinecone index '{index_name}' not found, creating one")
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric="euclidean",
            spec=PodSpec(environment=os.getenv("PINECONE_API_ENV"))
        )
        return pc.Index(index_name)

def create_multi_vector_retriever(
    text_summaries, texts, table_summaries, tables, image_summaries, images, index_name
):
    """
    Create a multi-vector retriever that indexes summaries and returns raw text, tables, or images.
    """
    vector_index = get_pinecone_index(index_name)

    # Initialize OpenAI embeddings
    # model_name = 'text-embedding-3-small'
    model_name = 'text-embedding-ada-002'
    embed = OpenAIEmbeddings(model=model_name, openai_api_key=os.getenv("OPENAI_API_KEY"))
    print(f"Initializing OpenAI embeddings with model: {model_name}")

    # Instantiate Pinecone vectorstore
    vectorstore = lc_pinecone(vector_index, embed.embed_query, "text")

    # Connect to PostgreSQL database
    connection_string = "postgresql+psycopg2://postgres:casperAI@104.154.107.148:5432/docstore"
    docstore_collection_name = index_name
    docstore = SQLDocStore(collection_name=docstore_collection_name, connection_string=connection_string)
    print("Connection to PostgreSQL DB successful")

    id_key = "doc_id"

    # Create the multi-vector retriever
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        id_key=id_key,
    )

    def add_documents(retriever, doc_summaries, doc_contents_with_page_numbers, add_page_number):
        """
        Add documents to the retriever's vectorstore and docstore.
        """
        doc_ids = [str(uuid.uuid4()) for _ in doc_contents_with_page_numbers]
        if add_page_number:
            page_numbers = [page_tuple[1] if len(page_tuple) >= 2 else page_tuple[0] for page_tuple in doc_contents_with_page_numbers]
        else:
            page_numbers = [-1]

        summary_docs = [
            Document(page_content=summary, metadata={"id_key": doc_id, "page_number": page_number})
            for doc_id, summary, page_number in zip(doc_ids, doc_summaries, page_numbers)
        ]
        retriever.vectorstore.add_documents(summary_docs)
        retriever.docstore.mset(list(zip(doc_ids, doc_contents_with_page_numbers)))

    # Add texts, tables, and images if they are not empty
    if text_summaries:
        add_documents(retriever, text_summaries, texts, True)
    if table_summaries:
        add_documents(retriever, table_summaries, tables, True)
    if image_summaries:
        add_documents(retriever, image_summaries, images, False)

    return retriever
