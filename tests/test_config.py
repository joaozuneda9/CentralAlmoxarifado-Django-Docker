import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.urls import reverse

from config.env import carregar_dotenv, ler_bool, ler_lista

RAIZ = Path(__file__).resolve().parent.parent
SENHA = "senha-de-teste-bem-comprida-123"
PRODUCAO = {
    "DEBUG": "0",
    "SECRET_KEY": secrets.token_urlsafe(64),
    "ALLOWED_HOSTS": "almoxarifado.saep.local",
    "USAR_HTTPS": "1",
    "PROXY_HTTPS": "0",
}


def rodar(args, **env):
    """Roda `python <args>` na raiz com config.settings (o pytest exporta settings_test).

    O subprocesso herda o ambiente, que já tem o .env lido pelo pytest, e não relê o .env: senão
    o .env preencheria a variável que o teste passa vazia (PREFIXO_URL="", por exemplo). Valor
    None tira a variável do ambiente do subprocesso."""
    ambiente = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "PYTHON_DOTENV_DISABLED": "1",
        **env,
    }
    ambiente = {nome: valor for nome, valor in ambiente.items() if valor is not None}
    return subprocess.run(
        [sys.executable, *args],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("1", True),
        ("true", True),
        ("Sim", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("nao", False),
        ("não", False),
        ("off", False),
    ],
)
def test_ler_bool_reconhece_valores(monkeypatch, valor, esperado):
    monkeypatch.setenv("X_TESTE", valor)
    assert ler_bool("X_TESTE", not esperado) is esperado


@pytest.mark.parametrize("valor", [None, "", "  "])
def test_ler_bool_vazio_usa_padrao(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("X_TESTE", raising=False)
    else:
        monkeypatch.setenv("X_TESTE", valor)
    assert ler_bool("X_TESTE", True) is True


def test_ler_bool_valor_invalido_recusa_com_o_nome(monkeypatch):
    monkeypatch.setenv("X_TESTE", "talvez")
    with pytest.raises(ImproperlyConfigured, match="X_TESTE"):
        ler_bool("X_TESTE", False)


def test_ler_lista(monkeypatch):
    monkeypatch.setenv("X_TESTE", " a.com, b.com ,, ")
    assert ler_lista("X_TESTE") == ["a.com", "b.com"]
    monkeypatch.delenv("X_TESTE")
    assert ler_lista("X_TESTE") == []


def test_producao_sem_secret_key_nao_sobe():
    r = rodar(["-c", "import django; django.setup()"], **{**PRODUCAO, "SECRET_KEY": ""})
    assert r.returncode != 0
    assert "SECRET_KEY" in r.stderr


def test_check_deploy_sem_avisos():
    r = rodar(["manage.py", "check", "--deploy", "--fail-level", "WARNING"], **PRODUCAO)
    assert r.returncode == 0, r.stdout + r.stderr


def test_check_deploy_sem_avisos_em_http_direto():
    """Produção em HTTP direto (USAR_HTTPS=0, deploy/AMBIENTES.md): o atualizar.ps1 roda o check
    com --fail-level WARNING e não pode parar nos avisos que são a própria decisão."""
    r = rodar(
        ["manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        **{**PRODUCAO, "USAR_HTTPS": "0"},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_http_direto_so_silencia_os_avisos_de_https():
    codigo = (
        "import django; django.setup(); from django.conf import settings; "
        "print(sorted(settings.SILENCED_SYSTEM_CHECKS))"
    )
    com = rodar(["-c", codigo], **PRODUCAO)
    sem = rodar(["-c", codigo], **{**PRODUCAO, "USAR_HTTPS": "0"})
    assert "security.W008" not in com.stdout, com.stderr
    for aviso in ("security.W004", "security.W008", "security.W012", "security.W016"):
        assert aviso in sem.stdout, sem.stderr


def test_proxy_https_liga_cabecalho_do_proxy():
    codigo = (
        "import django; django.setup(); from django.conf import settings; "
        "print(settings.SECURE_PROXY_SSL_HEADER)"
    )
    r = rodar(["-c", codigo], **{**PRODUCAO, "PROXY_HTTPS": "1"})
    assert "('HTTP_X_FORWARDED_PROTO', 'https')" in r.stdout, r.stderr


def test_usar_https_desligado_nao_redireciona():
    codigo = (
        "import django; django.setup(); from django.conf import settings; "
        "print(settings.SECURE_SSL_REDIRECT, settings.SESSION_COOKIE_SECURE)"
    )
    r = rodar(["-c", codigo], **{**PRODUCAO, "USAR_HTTPS": "0"})
    assert "False False" in r.stdout, r.stderr


def test_env_exemplo_nao_usa_variavel_https_do_cgi():
    """`HTTPS` é variável do CGI: o servidor de desenvolvimento (wsgiref) copia o ambiente para
    a requisição e passaria a tratar toda requisição http como https, recusando o CSRF."""
    linhas = (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
    assert not any(linha.startswith("HTTPS=") for linha in linhas)
    assert any(linha.startswith("USAR_HTTPS=") for linha in linhas)


def test_pasta_de_logs_e_criada_e_recebe_o_log(tmp_path):
    pasta = tmp_path / "logs" / "novo"
    codigo = (
        "import django, logging; django.setup(); "
        "logging.getLogger('almoxarifado').warning('teste de log')"
    )
    r = rodar(["-c", codigo], **{**PRODUCAO, "LOG_DIR": str(pasta)})
    assert r.returncode == 0, r.stderr
    assert "teste de log" in (pasta / "almoxarifado.log").read_text(encoding="utf-8")


@pytest.mark.django_db
def test_banco_e_mysql_e_guarda_acento_e_emoji():
    assert connection.vendor == "mysql"
    u = get_user_model().objects.create_user(
        username="1", password=SENHA, first_name="Conceição 🧽"
    )
    u.refresh_from_db()
    assert u.first_name == "Conceição 🧽"


@pytest.mark.django_db
def test_usuario_entra_por_matricula(client):
    assert settings.AUTH_USER_MODEL == "contas.Usuario"
    modelo = get_user_model()
    assert modelo._meta.get_field("username").verbose_name == "matrícula"
    modelo.objects.create_user(username="12345", password=SENHA)
    assert client.login(username="12345", password=SENHA)


@pytest.mark.django_db
def test_admin_de_usuarios_fala_em_matricula(admin_client):
    resposta = admin_client.get(reverse("admin:contas_usuario_add"))
    assert resposta.status_code == 200
    assert "Matrícula" in resposta.text


ATRAS_DO_APACHE = """
import django
django.setup()
from waitress.proxy_headers import proxy_headers_middleware
from config.wsgi import application

app = proxy_headers_middleware(
    application,
    trusted_proxy="127.0.0.1",
    trusted_proxy_headers={"x-forwarded-proto", "x-forwarded-for"},
)
ambiente = {
    "REQUEST_METHOD": "GET", "PATH_INFO": "/", "QUERY_STRING": "", "SERVER_NAME": "x",
    "SERVER_PORT": "8080", "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.url_scheme": "http",
    "REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": "almoxarifado.saep.local",
    "HTTP_X_FORWARDED_PROTO": "https", "HTTP_X_FORWARDED_FOR": "10.1.2.3",
    "wsgi.input": __import__("io").BytesIO(),
    "wsgi.errors": __import__("sys").stderr,
}
estado = []
app(ambiente, lambda status, cabecalhos, *a: estado.append(status))
print(estado[0])
"""


def test_atras_do_apache_com_waitress_documentado_nao_entra_em_laco():
    """Com PROXY_HTTPS=1 e o waitress confiando no X-Forwarded-Proto do Apache, a página abre
    em vez de redirecionar para https de novo. Sem `--trusted-proxy`, o waitress 3 descarta o
    cabeçalho e o redirecionamento vira laço; por isso o .env.example diz como rodar."""
    r = rodar(["-c", ATRAS_DO_APACHE], **{**PRODUCAO, "PROXY_HTTPS": "1"})
    assert r.stdout.strip().startswith("200"), r.stdout + r.stderr
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    assert "--trusted-proxy=127.0.0.1" in exemplo
    # x-forwarded-for: sem ele, todo pedido parece vir do Apache e divide o limite por IP.
    assert '--trusted-proxy-headers="x-forwarded-proto x-forwarded-for"' in exemplo


def test_log_aguenta_varios_processos():
    """O waitress e os comandos de importação gravam no mesmo log: no Windows, o
    `RotatingFileHandler` não consegue renomear o arquivo aberto por outro processo."""
    handler = settings.LOGGING["handlers"]["arquivo"]
    assert handler["class"] == "concurrent_log_handler.ConcurrentRotatingFileHandler"
    assert handler["maxBytes"] == 5 * 1024 * 1024
    assert handler["backupCount"] == 10


def test_padroes_do_scpi():
    codigo = (
        "import django; django.setup(); from django.conf import settings; "
        "print(settings.SCPI_URL, settings.SCPI_HEADLESS, "
        "settings.SCPI_PERFIL_DIR == settings.BASE_DIR / '.pw-profile', "
        "'scpi' in settings.INSTALLED_APPS)"
    )
    r = rodar(["-c", codigo], SCPI_URL="", SCPI_HEADLESS="", SCPI_PERFIL_DIR="")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == [
        "https://transparencia.saep.sp.gov.br:8445/scpi9/",
        "False",
        "True",
        "True",
    ]


def test_dotenv_preenche_variavel_ausente_ou_vazia_e_respeita_a_preenchida(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    linhas = ["A_AUSENTE=do-env", "A_VAZIA=do-env", "A_PREENCHIDA=do-env", "A_SEM_VALOR="]
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    # setenv + delenv registra o estado original (ausente), que o pytest restaura no fim.
    for nome in ("A_AUSENTE", "A_SEM_VALOR"):
        monkeypatch.setenv(nome, "x")
        monkeypatch.delenv(nome)
    monkeypatch.setenv("A_VAZIA", "")
    monkeypatch.setenv("A_PREENCHIDA", "do-sistema")
    carregar_dotenv(arquivo)
    assert os.environ["A_AUSENTE"] == "do-env"
    assert os.environ["A_VAZIA"] == "do-env"
    assert os.environ["A_PREENCHIDA"] == "do-sistema"
    assert "A_SEM_VALOR" not in os.environ


def test_dotenv_expande_referencias_com_o_ambiente_na_frente(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text("BANCO_NOME=do-env\nBANCO_HOST=${BANCO_NOME}\n", encoding="utf-8")
    monkeypatch.setenv("BANCO_NOME", "do-sistema")
    monkeypatch.delenv("BANCO_HOST", raising=False)
    carregar_dotenv(arquivo)
    assert os.environ["BANCO_NOME"] == "do-sistema"
    assert os.environ["BANCO_HOST"] == "do-sistema"
    monkeypatch.delenv("BANCO_HOST")


def test_dotenv_desligado_pelo_ambiente_nao_le_o_arquivo(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text("A_DESLIGADA=do-env\n", encoding="utf-8")
    monkeypatch.delenv("A_DESLIGADA", raising=False)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    carregar_dotenv(arquivo)
    assert "A_DESLIGADA" not in os.environ


def test_env_exemplo_documenta_a_implantacao():
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    for variavel in [
        "LANCAMENTO_REAL",
        "BACKUP_DIR",
        "MYSQLDUMP",
        "PLAYWRIGHT_BROWSERS_PATH",
        "SCPI_HEADLESS",
        "PREFIXO_URL",
    ]:
        assert f"\n{variavel}=" in exemplo, variavel
