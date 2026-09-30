FROM python:3.12-slim-bullseye

ENV LANG=en_US.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=0 \
    PYTHONWARNINGS="ignore:Unverified HTTPS request"

RUN apt update && apt install -y git

# Create app directory
WORKDIR /opt/app

ARG GITLAB_TOKEN_NAME
ARG GITLAB_TOKEN

COPY poetry.lock pyproject.toml /opt/app/

RUN echo "https://${GITLAB_TOKEN_NAME}:${GITLAB_TOKEN}@gitlab.forcode.pro" > $HOME/.git-credentials && \
    git config --global credential.helper store &&\
    pip install --upgrade pip &&\
    pip install "poetry==$POETRY_VERSION" &&\
    poetry install --no-interaction

COPY . .

COPY docker-entrypoint.sh /usr/local/bin/

ENTRYPOINT ["docker-entrypoint.sh"]
