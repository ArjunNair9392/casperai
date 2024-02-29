FROM python:3.9-slim

WORKDIR /app

# Installing poppler and tesseract
RUN apt-get update && \
apt-get install -y \
libpoppler-cpp-dev \
poppler-utils \
tesseract-ocr \
tesseract-ocr-eng \
&& rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt ./requirements.txt
COPY extraction.py ./extraction.py
COPY generate_summaries.py ./generate_summaries.py
COPY upload_service.py ./uploadApp.py
RUN pip install -r requirements.txt

EXPOSE 8080

CMD ["python", "uploadApp.py"]