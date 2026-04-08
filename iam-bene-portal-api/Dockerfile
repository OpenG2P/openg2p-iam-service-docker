FROM python:3.12.11-alpine3.22

RUN apk add --no-cache --virtual .build-deps gcc libc-dev linux-headers make \
 && apk add --no-cache bash git gettext libpq-dev libmagic

WORKDIR /app

COPY local_deps/ /app/local_deps/
COPY adapters.requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1
ENV IAM_API_NO_OF_WORKERS=2
ENV IAM_API_HOST=0.0.0.0
ENV IAM_API_PORT=8000
ENV IAM_API_WORKER_TYPE=gunicorn

CMD python3 -m iam_bene_portal_api.main migrate; \
    gunicorn "iam_bene_portal_api.main:app" --workers ${IAM_API_NO_OF_WORKERS} --worker-class uvicorn.workers.UvicornWorker --bind ${IAM_API_HOST}:${IAM_API_PORT}
