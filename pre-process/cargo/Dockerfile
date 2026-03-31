FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace

WORKDIR /workspace

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY cargo/docker-entrypoint.sh /usr/local/bin/preprocess-cargo

RUN chmod +x /usr/local/bin/preprocess-cargo

ENTRYPOINT ["preprocess-cargo"]
CMD ["status"]
