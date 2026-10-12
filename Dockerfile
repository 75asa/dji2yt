FROM python:3.14-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
# Mount config.toml / token.json / state.db under /data
WORKDIR /data
ENTRYPOINT ["dji2yt", "-c", "/data/config.toml"]
CMD ["run"]
