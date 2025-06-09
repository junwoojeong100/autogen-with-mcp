FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY weather_sse_apim.py .

EXPOSE 8000

CMD ["python", "weather_sse_apim.py"]
