# ─── Stage 1: Build the Nuxt frontend ────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

# Install dependencies first (layer cache)
COPY frontend/package*.json ./
RUN npm install

# Copy source and build static output
COPY frontend/ ./
RUN npm run generate


# ─── Stage 2: Python backend + static frontend ────────────────────────────────
FROM python:3.12-slim AS backend

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend into the location the backend expects
COPY --from=frontend-builder /app/frontend/.output/public ./backend/static/

# Copy the MasterDnsVPN binary (needed so the service-controller routes don't
# crash on startup; service management itself requires systemd which is not
# present in the container)
COPY backend/bin/ ./backend/bin/

# Create the data directory for profile storage
RUN mkdir -p ./data

WORKDIR /app/backend

ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["python", "main.py"]
