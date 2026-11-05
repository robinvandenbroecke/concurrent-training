FROM node:24-bookworm-slim AS webapp
WORKDIR /webapp
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci
COPY webapp/ ./
RUN npm test
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    AUTO_CREATE_TABLES=false \
    REQUIRE_API_KEY=true
WORKDIR /srv/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY static/ ./static/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY deployment/ ./deployment/
COPY --from=webapp /webapp/dist ./webapp/dist/
RUN useradd --uid 10001 --create-home appuser
USER appuser
EXPOSE 10000
CMD ["python", "-m", "deployment.serve"]
