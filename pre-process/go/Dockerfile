FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace

WORKDIR /workspace

COPY requirements.txt /tmp/preprocess-go-requirements.txt

RUN pip install --no-cache-dir -r /tmp/preprocess-go-requirements.txt

COPY docker-entrypoint.sh /usr/local/bin/preprocess-go

RUN chmod +x /usr/local/bin/preprocess-go

ENTRYPOINT ["preprocess-go"]
CMD ["build"]
