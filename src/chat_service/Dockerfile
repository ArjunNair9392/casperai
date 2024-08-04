FROM python:3.9-slim-buster

WORKDIR /app

RUN apt-get update && \
apt-get install -y \
postgresql-client \
libpq-dev gcc \
&& rm -rf /var/lib/apt/lists/*

COPY ./requirements_for_chat.txt ./requirements_for_chat.txt
COPY chat_service.py ./chat_service.py
COPY chat_service_helper.py ./chat_service_helper.py
COPY docstore/ ./docstore/
COPY retriever/ ./retriever/
RUN pip install --no-cache-dir -r requirements_for_chat.txt


EXPOSE 8080

CMD ["python", "chat_service.py"]