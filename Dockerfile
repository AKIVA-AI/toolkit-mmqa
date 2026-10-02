FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src/ ./src/
RUN pip install --no-cache-dir ".[image,audio,fast,signing]" && useradd --create-home mmqa
USER mmqa
WORKDIR /data
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["toolkit-mmqa"]
CMD ["--help"]
