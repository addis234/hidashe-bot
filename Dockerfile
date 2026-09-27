FROM python:3.10-slim

# Pillow እና Tesseract የሚያስፈልጋቸውን የሲስተም ላይብረሪዎች መጫን
RUN apt-get update && apt-get install -y \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt-get/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
