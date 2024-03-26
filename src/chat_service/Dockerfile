FROM python:3.9-slim

WORKDIR /app


COPY ./requirements.txt ./requirements.txt
COPY chat_service.py ./chatApp.py
RUN pip install -r requirements.txt

OPENAI_API_KEY  = "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"

PINECONE_API_KEY= "00644595-2a4e-4d0f-8c63-1f22f1b7332a"

EXPOSE 8080

CMD ["python", "chatApp.py"]