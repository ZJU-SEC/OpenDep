FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace
ENV MAVEN_PREPROCESS_REPOSITORY_ROOT=/root/.m2/repository

WORKDIR /workspace

COPY pre-process /workspace/pre-process
COPY pre-process/maven/docker-entrypoint.sh /usr/local/bin/preprocess-maven

RUN chmod +x /usr/local/bin/preprocess-maven && \
    mkdir -p /root/.m2/repository

ENTRYPOINT ["preprocess-maven"]
CMD ["build.py", "--help"]
