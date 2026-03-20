FROM cnspary/pip-resolver-base:latest

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

LABEL resolver.ecosystem="pip"
LABEL resolver.stage="active"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN python3 -m pip install --no-cache-dir \
    packaging \
    resolvelib \
    "psycopg[binary]>=3.1"

CMD ["python3", "Resolver/containerization/runtime/pip_adapter.py"]
