FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .
COPY blogs.yaml ./

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz', timeout=3)"

CMD ["python", "-m", "recipes_mcp"]
