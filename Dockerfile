FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git libgl1-mesa-glx libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e ".[dev]"
RUN mkdir -p /app/datasets /app/reports
ENV PYTHONUNBUFFERED=1
CMD ["toolkit-mmqa", "--help"]
