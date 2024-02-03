from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain.storage import InMemoryStore
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Pinecone
from haystack.document_stores.faiss import FAISSDocumentStore
from pinecone import Pinecone, PodSpec


import uuid
import os

def get_vectorestore():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index_name = "casperai"
    if index_name not in pc.list_indexes():
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric="cosine",
            spec=PodSpec(environment=os.getenv("PINECONE_API_ENV"))
        )

    index = pc.Index(index_name)

    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

    model_name = 'text-embedding-ada-002'

    embed = OpenAIEmbeddings(
        model=model_name,
        openai_api_key=OPENAI_API_KEY
    )

    # Instantiate Pinecone vectorstore
    vectorstore = Pinecone(index, embed.embed_query, "text")

    return vectorstore

def create_multi_vector_retriever(
    text_summaries, texts, table_summaries, tables, image_summaries, images
):
    """
    Create retriever that indexes summaries, but returns raw images or texts
    """
    # Pinecode vectorstore
    vectorstore = get_vectorestore()

    # Initialize the storage layer
    # Initialize the SQLite storage layer
    store = FAISSDocumentStore(sql_url="sqlite:////Users/arjunnair/Workspace/casperai/src/database/doc_store.sqlite", faiss_index_factory_str="Flat")
    id_key = "doc_id"

    # Create the multi-vector retriever
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=store,
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