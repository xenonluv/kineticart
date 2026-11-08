# kinerag-embed: 로컬 e5-large 질의 임베딩 + 갤러리 유사도 검색(무료·무API, 내부 전용)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
ENV FASTEMBED_CACHE=/models PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "server.py"]
