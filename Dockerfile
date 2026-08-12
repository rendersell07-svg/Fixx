# Python 3.11 का हल्का इमेज
FROM python:3.11-slim

# ffmpeg (ffprobe सहित) इंस्टॉल करें
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# कार्य निर्देशिका सेट करें
WORKDIR /app

# पहले requirements.txt कॉपी करें (कैशिंग के लिए)
COPY requirements.txt .

# Python डिपेंडेंसी इंस्टॉल करें
RUN pip install --no-cache-dir -r requirements.txt

# बाकी सारी फ़ाइलें कॉपी करें
COPY . .

# बॉट चलाएँ
CMD ["python", "main.py"]
