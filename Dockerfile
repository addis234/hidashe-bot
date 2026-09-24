FROM python:3.10-slim

# Tesseract OCR ን መጫን
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements መጫን
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# የቦቱን ፋይሎች ኮፒ ማድረግ
COPY . .

# ቦቱን ማስነሳት
CMD ["python", "bot.py"]
