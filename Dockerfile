FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements-large.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir pyspark==4.0.0
COPY . .
RUN mkdir -p data/uploads data/outputs data/errors data/reports data/templates
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
