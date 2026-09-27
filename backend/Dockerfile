FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libarchive-tools hunspell-sr \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 RUFF_NO_CACHE=true
WORKDIR /app
COPY requirements.txt requirements-dev.txt constraints.txt ./
RUN pip install --no-cache-dir -c constraints.txt -r requirements-dev.txt
COPY . .

CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
