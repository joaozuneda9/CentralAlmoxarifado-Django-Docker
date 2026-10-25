"""Settings do Central Almoxarifado.

Um único módulo para todos os ambientes: os valores vêm do `.env` (ou do ambiente do
sistema, que tem precedência). Com `DEBUG` desligado, valem as proteções de produção.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import carregar_dotenv, ler_bool, ler_lista

BASE_DIR = Path(__file__).resolve().parent.parent

# Variável já preenchida no ambiente vence o .env (vazia, não).
carregar_dotenv(BASE_DIR / ".env")

DEBUG = ler_bool("DEBUG", False)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Defina SECRET_KEY no .env.")
    SECRET_KEY = "dev-inseguro-somente-local"

ALLOWED_HOSTS = ler_lista("ALLOWED_HOSTS")
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = ler_lista("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "contas",
    "interface",
    "pedidos",
    "catalogo",
    "scpi",
    "automacoes",
    "implantacao",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Depois da autenticação: a Segurança do Trabalho só abre as rotas da lista (spec 008).
    "contas.middleware.RestringirSegurancaTrabalho",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "interface.navegacao.menu",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME") or "almoxarifado",
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST") or "127.0.0.1",
        "PORT": os.environ.get("DB_PORT") or "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
    }
}

AUTH_USER_MODEL = "contas.Usuario"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "pedidos:painel"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# Prefixo do site atrás do Apache (ex.: /almoxarifado), o mesmo do --url-prefix do waitress.
# O waitress só informa o prefixo a cada pedido, mas o STATIC_URL é lido na partida: sem
# isto, os links dos arquivos estáticos sairiam sem o prefixo (/static/...) e o Apache os
# recusaria. Vazio = o site na raiz.
PREFIXO_URL = (os.environ.get("PREFIXO_URL") or "").strip().strip("/")
PREFIXO_URL = f"/{PREFIXO_URL}" if PREFIXO_URL else ""
FORCE_SCRIPT_NAME = PREFIXO_URL or None
STATIC_URL = f"{PREFIXO_URL}/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Credenciais do SCPI (robôs) e do Telegram (avisos de pedido).
SAEP_USER = os.environ.get("SAEP_USER", "")
SAEP_PASS = os.environ.get("SAEP_PASS", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
# Chat da Segurança do Trabalho: avisado dos pedidos de EPI que aguardam autorização (spec 008).
TELEGRAM_CHAT_ID_SEGURANCA = os.environ.get("TELEGRAM_CHAT_ID_SEGURANCA", "")

# Proteção dos formulários públicos de pedido (spec, fluxo 1). Aparelhos atrás do mesmo IP
# (rede de operadora ou NAT) dividem o limite por IP.
PEDIDOS_LIMITE_IP_10_MIN = 3
PEDIDOS_LIMITE_IP_DIA = 10
PEDIDOS_LIMITE_SOLICITANTE_DIA = 5
PEDIDOS_TEMPO_MINIMO = 5  # segundos entre abrir o formulário e enviar
PEDIDOS_MAX_ITENS = 40
PEDIDOS_MAX_TEXTO = 200
PEDIDOS_CONSULTA_LIMITE_IP_10_MIN = 20  # consultas do resultado de um pedido de EPI, por rede

# Navegador dos robôs do SCPI (Playwright). Cada tipo de importação usa uma subpasta própria
# do perfil, para tipos diferentes poderem rodar ao mesmo tempo.
SCPI_URL = os.environ.get("SCPI_URL") or "https://transparencia.saep.sp.gov.br:8445/scpi9/"
SCPI_HEADLESS = ler_bool("SCPI_HEADLESS", False)
SCPI_PERFIL_DIR = Path(os.environ.get("SCPI_PERFIL_DIR") or BASE_DIR / ".pw-profile")
# Trava do lançamento real no SCPI. Desligada (o padrão), só a simulação roda. Liga só no
# ambiente que lança de verdade (a produção): uma cópia de desenvolvimento ou de teste com as
# mesmas saídas pendentes lançaria em dobro.
LANCAMENTO_REAL = ler_bool("LANCAMENTO_REAL", False)

if not DEBUG:
    # Não use o nome HTTPS: é variável do CGI, e o wsgiref (runserver) a copia para a
    # requisição, que passaria a parecer https.
    USAR_HTTPS = ler_bool("USAR_HTTPS", True)
    SECURE_SSL_REDIRECT = USAR_HTTPS
    SESSION_COOKIE_SECURE = USAR_HTTPS
    CSRF_COOKIE_SECURE = USAR_HTTPS
    if USAR_HTTPS:
        SECURE_HSTS_SECONDS = 3600
    # Atrás do Apache, o HTTPS termina no proxy; sem este cabeçalho o redirecionamento
    # para HTTPS entraria em laço.
    if ler_bool("PROXY_HTTPS", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # HSTS com subdomínios e preload depende do domínio de produção, que ainda não está
    # definido: silenciados até essa decisão.
    SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

LOG_DIR = Path(os.environ.get("LOG_DIR") or BASE_DIR / "logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Backup diário do banco (comando backup_banco), fora do repositório.
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR") or BASE_DIR.parent / "backups-almoxarifado")
BACKUP_RETENCAO_DIAS = 60
# mysqldump (MySQL) ou mariadb-dump (MariaDB), com o caminho se não estiver no PATH.
MYSQLDUMP = os.environ.get("MYSQLDUMP") or "mysqldump"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "padrao": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "padrao"},
        # Vários processos gravam aqui (waitress e comandos de importação); no Windows, o
        # RotatingFileHandler não renomeia um arquivo que outro processo mantém aberto.
        "arquivo": {
            "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
            "filename": LOG_DIR / "almoxarifado.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 10,
            "encoding": "utf-8",
            "formatter": "padrao",
        },
    },
    "root": {"handlers": ["console", "arquivo"], "level": "INFO"},
}
