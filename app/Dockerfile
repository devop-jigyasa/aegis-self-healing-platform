# --- Stage 1: Build Dependencies ---
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Stage 2: Hardened Runtime Container ---
FROM python:3.11-slim AS runner

WORKDIR /app

# Security: Create unprivileged non-root user (UID 10001)
RUN groupadd -r aegisgroup && useradd -r -g aegisgroup -u 10001 aegisuser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/aegisuser/.local
ENV PATH=/home/aegisuser/.local/bin:$PATH

# Copy application source code & assets
COPY main.py .
COPY static ./static

# Enforce secure file ownership
RUN chown -R aegisuser:aegisgroup /app /home/aegisuser

USER aegisuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
