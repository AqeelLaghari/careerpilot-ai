# CareerPilot AI backend: one container with FastAPI + all the AI models.
# The same image runs locally (docker compose), in CI (smoke test) and on Hugging Face Spaces.
#
#   docker build -t careerpilot-backend backend
#   docker run -p 7860:7860 --env-file backend/.env careerpilot-backend
#
# Secrets (Gemini key, Firebase key) are NEVER copied into the image: they are passed in
# at run time as environment variables / a mounted file (see docker-compose.yml).

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    PORT=7860 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface

# libgomp1: OpenMP, needed by FAISS and CTranslate2 (Whisper)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs containers as user 1000; never run as root
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

# 1) Dependencies first (cached between builds unless requirements.txt changes).
#    PyTorch CPU-only build: ~200 MB instead of ~2 GB with GPU libraries we don't use.
COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

USER user

# 2) Download the AI models into the image, so the server starts fast and works offline:
#    SBERT (career/ATS matching) and Whisper "base" (interview speech-to-text)
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2')" \
    && python -c "from faster_whisper import WhisperModel as W; W('base', device='cpu', compute_type='int8')"

# 3) The application code (changes most often, so it comes last)
COPY --chown=user:user . .
RUN mkdir -p data/raw

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fs "http://localhost:${PORT}/health" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
