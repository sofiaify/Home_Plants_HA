ARG BUILD_FROM=python:3.12-slim
FROM $BUILD_FROM

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLANTS_DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends tzdata bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
