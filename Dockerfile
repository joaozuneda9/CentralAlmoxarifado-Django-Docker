# Imagem do Central Almoxarifado: Django + waitress, Chromium do Playwright (robôs do SCPI),
# cliente do MariaDB (backup) e supercronic (agendador). Serve aos serviços "web" e
# "agendador" do compose.yaml.

# Etapa de construção: compila o mysqlclient e monta o .venv.
FROM python:3.13-slim-bookworm AS construcao
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config libmariadb-dev \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# Imagem final.
FROM python:3.13-slim-bookworm
ENV PATH=/app/.venv/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TZ=America/Sao_Paulo \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1

# supercronic (x86-64), conferido pelo SHA-1 publicado no release.
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.49/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=e63c11a9726b775a6a11801e81af4f3fb926aa68 \
    SUPERCRONIC=supercronic-linux-amd64
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmariadb3 mariadb-client tzdata ca-certificates curl \
 && curl -fsSLO "$SUPERCRONIC_URL" \
 && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
 && chmod +x "$SUPERCRONIC" \
 && mv "$SUPERCRONIC" /usr/local/bin/supercronic \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY --from=construcao /app/.venv /app/.venv
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
# O código fica do root e só para leitura; o almox escreve só em /dados. O collectstatic roda
# aqui com uma chave descartável: o manifesto não depende do PREFIXO_URL.
RUN SECRET_KEY=construcao DEBUG=0 LOG_DIR=/tmp/logs python manage.py collectstatic --noinput \
 && rm -rf /tmp/logs \
 && chmod +x deploy/*.sh \
 && useradd --uid 1000 --create-home almox \
 && mkdir -p /dados/logs /dados/backups /dados/perfil /dados/importacao \
 && chown almox:almox /dados/logs /dados/backups /dados/perfil

# O SHA muda a cada commit; so entra depois dos RUN para preservar o cache das instalacoes.
ARG REVISAO_APP=nao-identificada
LABEL org.opencontainers.image.source="https://github.com/joaozuneda9/CentralAlmoxarifado-Django-Docker" \
      org.opencontainers.image.revision="${REVISAO_APP}"

USER almox
EXPOSE 8010
CMD ["python", "-m", "waitress", "--listen=0.0.0.0:8010", "config.wsgi:application"]
