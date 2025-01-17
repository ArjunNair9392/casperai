FROM python:3.9

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
libpq-dev \
gcc \
libxext6 \
unoconv \
libreoffice \
&& rm -rf /var/lib/apt/lists/*

# Set PYTHONPATH environment variable
ENV PYTHONPATH="/usr/lib/libreoffice/program"

COPY ./requirements_latest.txt ./requirements_latest.txt
COPY extraction.py ./extraction.py
COPY retriever.py ./retriever.py
COPY generate_summaries.py ./generate_summaries.py
COPY upload_service.py ./uploadApp.py
COPY logging_config.py ./logging_config.py
COPY upload_service_helper.py ./upload_service_helper.py
COPY templates/ ./templates/
COPY docstore/ ./docstore/
RUN pip install --upgrade pip && \
    pip install --default-timeout=1000  -r requirements_latest.txt

EXPOSE 8080

RUN sed -i 's|#!/usr/bin/env python3|#!/usr/bin/python3|' /usr/bin/unoconv

CMD ["python3", "uploadApp.py"]