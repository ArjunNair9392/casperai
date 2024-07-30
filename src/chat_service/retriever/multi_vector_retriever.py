from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain_core.retrievers import Document


class CustomMultiVectorRetriever(MultiVectorRetriever):
    def get_relevant_documents(self, query, limit=None):
        # Retrieve document IDs from vectorstore
        docs = self.vectorstore.similarity_search(query, **self.search_kwargs)
        doc_ids = [doc.metadata['doc_id'] for doc in docs]

        # Fetch documents from docstore using the retrieved IDs
        documents = self.docstore.mget(doc_ids)

        return [Document(page_content=content, metadata=meta_data) for doc_id, (content, meta_data) in
                documents.items()]
