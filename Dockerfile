# syntax=docker/dockerfile:1.7

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app

USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD python -c "import os; print(1)"

CMD ["python", "bot.py"]
