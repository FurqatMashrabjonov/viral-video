# Frontend bundle, built once and handed to the API image. Node never appears
# in the final image -- a multi-stage build leaves the toolchain in stage one.
FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

FROM python:3.11-slim

# ffmpeg with libass is the one hard system dependency. The grep makes a
# missing build fail at image build time instead of at first request.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fontconfig \
    && ffmpeg -version | grep -q -- '--enable-libass' \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=web /static/app /app/static/app
COPY api.py db.py pipeline.py enhance.py analyze.py normalize.py subtitles.py \
     scribe.py settings.py cost.py ./
COPY fonts fonts
COPY luts luts
COPY sfx sfx
COPY styles styles
COPY static/index.html static/index.html

# State (sqlite + media) lives on a volume so it survives container rebuilds.
VOLUME /app/data

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
