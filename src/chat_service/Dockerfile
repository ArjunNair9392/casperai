FROM python:3.9-slim-buster

WORKDIR /app

RUN apt-get update && \
apt-get install -y \
postgresql-client \
libpq-dev gcc \
&& rm -rf /var/lib/apt/lists/*

COPY ./requirements_for_chat.txt ./requirements_for_chat.txt
COPY chat_service.py ./chatApp2.py
RUN pip install -r requirements_for_chat.txt


EXPOSE 8080

CMD ["python", "chatApp2.py"]