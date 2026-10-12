FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 10001 -m app
COPY ads_mcp ./ads_mcp
COPY static ./static
RUN mkdir -p /app/data && chown -R app:app /app/data
USER app
EXPOSE 8080
CMD ["uvicorn", "ads_mcp.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
