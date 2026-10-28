FROM python:3.11-slim

WORKDIR /app

RUN groupadd -r aegisgroup && useradd -r -g aegisgroup -u 10002 aegiscontroller

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY circuit_breaker.py .
COPY aiops_engine.py .
COPY remediation_bot.py .

RUN chown -R aegiscontroller:aegisgroup /app

USER aegiscontroller

EXPOSE 5000

CMD ["python", "remediation_bot.py"]
