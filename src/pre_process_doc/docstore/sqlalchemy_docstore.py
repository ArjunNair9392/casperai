from langchain_core.stores import BaseStore
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import json

Base = declarative_base()


class DocumentStore(Base):
    __tablename__ = 'documents'

    doc_id = Column(String, primary_key=True)
    content = Column(Text)
    meta_data = Column(Text)  # Store meta_data as JSON string

    def __init__(self, doc_id, content, meta_data):
        self.doc_id = doc_id
        self.content = content
        self.meta_data = json.dumps(meta_data)  # Serialize to JSON


class SQLAlchemyDocStore(BaseStore):
    def __init__(self, db_url, namespace):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.namespace = namespace

    def mset(self, documents):
        session = self.Session()
        for doc_id, content, meta_data in documents:
            doc = DocumentStore(doc_id=doc_id, content=content, meta_data=meta_data)
            session.add(doc)
        session.commit()
        session.close()

    def mget(self, doc_ids):
        session = self.Session()
        docs = session.query(DocumentStore).filter(DocumentStore.doc_id.in_(doc_ids)).all()
        session.close()
        return {doc.doc_id: (doc.content, json.loads(doc.meta_data)) for doc in docs}  # Deserialize JSON

    def mdelete(self, doc_ids):
        session = self.Session()
        session.query(DocumentStore).filter(DocumentStore.doc_id.in_(doc_ids)).delete(synchronize_session='fetch')
        session.commit()
        session.close()

    def yield_keys(self, namespace=None):
        session = self.Session()
        query = session.query(DocumentStore.doc_id)
        if namespace:
            query = query.filter(DocumentStore.meta_data.like(f'%"{namespace}"%'))  # Search in JSON field
        doc_ids = query.all()
        session.close()
        for doc_id, in doc_ids:
            yield doc_id
