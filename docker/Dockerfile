FROM nousresearch/hermes-agent:latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client curl netcat-openbsd iputils-ping \
    && rm -rf /var/lib/apt/lists/*
