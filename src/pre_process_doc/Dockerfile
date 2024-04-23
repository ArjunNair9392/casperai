FROM python:3.9-slim-buster

WORKDIR /app

# Installing poppler and tesseract
RUN apt-get update && \
apt-get install -y \
libpoppler-cpp-dev \
poppler-utils \
tesseract-ocr \
tesseract-ocr-eng \
ffmpeg \
libsm6 \
libxext6 \
&& rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt ./requirements.txt
COPY extraction.py ./extraction.py
COPY retriever.py ./retriever.py
COPY generate_summaries.py ./generate_summaries.py
COPY upload_service.py ./uploadApp.py
COPY token ./token
RUN pip install -r requirements.txt

EXPOSE 8080

CMD ["python", "uploadApp.py"]