FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV PORT=8000
CMD gunicorn -w 1 --threads 8 --access-logfile - -b 0.0.0.0:$PORT app.main:app
