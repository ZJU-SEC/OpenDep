FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace

WORKDIR /workspace

COPY requirements /tmp/requirements
COPY pip/requirements.txt /tmp/pip/requirements.txt

RUN pip install --no-cache-dir -r /tmp/pip/requirements.txt

COPY pip/docker-entrypoint.sh /usr/local/bin/preprocess-pip

RUN chmod +x /usr/local/bin/preprocess-pip

ENTRYPOINT ["preprocess-pip"]
CMD ["build"]
