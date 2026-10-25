"""Ajustes só para o pytest."""

import os

os.environ.setdefault("SECRET_KEY", "teste-nao-usar-em-producao")

from .settings import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Sem collectstatic nos testes: o whitenoise lê os arquivos a cada requisição.
WHITENOISE_AUTOREFRESH = True
# Nenhum teste avisa no Telegram de verdade, mesmo com o .env de desenvolvimento preenchido.
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""
TELEGRAM_CHAT_ID_SEGURANCA = ""
# Os testes rodam o site na raiz, mesmo com PREFIXO_URL no .env de desenvolvimento; o prefixo
# tem testes próprios (tests/test_prefixo.py e o teste de configuração em subprocesso).
PREFIXO_URL = ""
FORCE_SCRIPT_NAME = None
STATIC_URL = "/static/"
# Os testes do robô exercitam o lançamento real; o bloqueio tem o próprio arquivo de testes
# (Decisão 9 do plano do subprojeto 5).
LANCAMENTO_REAL = True
