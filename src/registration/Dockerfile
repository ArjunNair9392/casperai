FROM python:3.9-slim-buster

WORKDIR /app

COPY ./requirements.txt ./requirements.txt
COPY ./utility_functions.py ./utility_functions.py
COPY registration_service.py ./registration_service.py
RUN pip install -r requirements.txt


EXPOSE 8080

CMD ["python", "registration_service.py"]