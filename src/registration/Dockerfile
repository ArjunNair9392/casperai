FROM python:3.9-slim-buster

WORKDIR /app

COPY ./requirements.txt ./requirements.txt
COPY registration.py ./registration.py
RUN pip install -r requirements.txt


EXPOSE 8080

CMD ["python", "registration.py"]