FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace

WORKDIR /workspace

COPY requirements.txt /tmp/preprocess-npm-requirements.txt

RUN pip install --no-cache-dir -r /tmp/preprocess-npm-requirements.txt

COPY npm/docker-entrypoint.sh /usr/local/bin/preprocess-npm

RUN chmod +x /usr/local/bin/preprocess-npm

ENTRYPOINT ["preprocess-npm"]
CMD ["build"]
