# --- Stage 1: Build Dependencies ---
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Stage 2: Hardened Runtime Container ---
FROM python:3.11-slim AS runner

WORKDIR /app

# Security: Create unprivileged non-root user (UID 10002)
RUN groupadd -r aegisgroup && useradd -r -m -g aegisgroup -u 10002 aegiscontroller

# Copy installed packages from builder
COPY --from=builder /root/.local /home/aegiscontroller/.local
ENV PATH=/home/aegiscontroller/.local/bin:$PATH

# Copy controller modules
COPY circuit_breaker.py .
COPY aiops_engine.py .
COPY remediation_bot.py .

# Enforce secure file ownership
RUN chown -R aegiscontroller:aegisgroup /app /home/aegiscontroller

USER aegiscontroller

EXPOSE 5000

CMD ["uvicorn", "remediation_bot:app", "--host", "0.0.0.0", "--port", "5000"]
