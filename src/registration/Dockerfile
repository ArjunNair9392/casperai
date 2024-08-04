FROM python:3.9-slim-buster

WORKDIR /app

COPY ./requirements.txt ./requirements.txt
COPY registration_service_helper.py ./registration_service_helper.py
COPY registration_service.py ./registration_service.py
RUN pip install -r requirements.txt


EXPOSE 8080

CMD ["python", "registration_service.py"]