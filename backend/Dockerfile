FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Scribe's supported SDK needs websockets>=13; the proven inference backend
# keeps its own dependencies. Only the caption subprocess uses this venv.
COPY backend/requirements-captions.txt /tmp/requirements-captions.txt
RUN python -m venv /opt/matchpulse-captions \
    && /opt/matchpulse-captions/bin/pip install --no-cache-dir -r /tmp/requirements-captions.txt
ENV MATCHPULSE_CAPTION_PYTHON=/opt/matchpulse-captions/bin/python

COPY backend/ ./backend/
COPY frontend/sports-streaming-service/src/data/matches.json ./frontend/sports-streaming-service/src/data/matches.json

EXPOSE 8000 8031

CMD ["python", "-m", "backend.main"]
