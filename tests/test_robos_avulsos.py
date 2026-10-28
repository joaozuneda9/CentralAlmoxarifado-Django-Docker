"""Execução avulsa dos robôs (abas do Catálogo e opções do lançamento), sem abrir o navegador."""

import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from catalogo import forms as formularios
from catalogo.forms import RoboCadastroForm, RoboEstoqueForm, RoboSaidasForm
from catalogo.models import Importacao, Material
from pedidos.forms import LancamentoForm
from scpi.disparo import guardar_csv_enviado, iniciar_importacao, iniciar_lancamento
from tests.cenario import criar_pedido

pytestmark = pytest.mark.django_db

LANCAMENTOS = reverse("automacoes:pagina") + "?aba=lancamento"
FIXTURES = Path(__file__).parent / "fixtures" / "scpi"


@pytest.fixture
def processos(monkeypatch, settings, tmp_path):
    """Troca o Popen por um registro dos argumentos e manda o log para uma pasta temporária."""
    settings.LOG_DIR = tmp_path
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: chamadas.append(args))
    return chamadas


def csv(nome="dados.csv", conteudo=b"a;b\n1;2\n"):
    return SimpleUploadedFile(nome, conteudo, content_type="text/csv")


# ---- formulários -------------------------------------------------------------------------------


def test_origem_csv_exige_um_arquivo_valido():
    assert not RoboEstoqueForm({"origem": "csv"}).is_valid()
    assert "Escolha o arquivo CSV." in RoboEstoqueForm({"origem": "csv"}).errors["arquivo"]
    vazio = RoboEstoqueForm({"origem": "csv"}, {"arquivo": csv(conteudo=b"")})
    assert vazio.errors["arquivo"] == ["O arquivo enviado está vazio."]
    errado = RoboEstoqueForm({"origem": "csv"}, {"arquivo": csv("dados.xlsx")})
    assert "Envie um arquivo .csv." in errado.errors["arquivo"]
    assert RoboEstoqueForm({"origem": "csv"}, {"arquivo": csv()}).is_valid()


def test_arquivo_grande_demais_e_recusado(monkeypatch):
    monkeypatch.setattr(formularios, "TAMANHO_MAXIMO_CSV", 4)
    form = RoboEstoqueForm({"origem": "csv"}, {"arquivo": csv(conteudo=b"12345")})
    assert "O arquivo passa de 25 MB." in form.errors["arquivo"]


def test_origem_scpi_ignora_o_arquivo_enviado():
    form = RoboEstoqueForm({"origem": "scpi"}, {"arquivo": csv()})
    assert form.is_valid() and form.cleaned_data["arquivo"] is None


def test_periodo_das_saidas_confere_ordem_e_futuro():
    hoje = timezone.localdate()
    invertido = RoboSaidasForm({"origem": "scpi", "desde": "2026-10-10", "ate": "2026-10-01"})
    assert "O fim do período é antes do início." in invertido.errors["ate"]
    futuro = RoboSaidasForm({"origem": "scpi", "ate": (hoje + timedelta(days=1)).isoformat()})
    assert "O fim do período não pode ser no futuro." in futuro.errors["ate"]
    assert RoboSaidasForm({"origem": "scpi", "desde": "2026-10-01", "ate": "2026-10-10"}).is_valid()
    vazio = RoboSaidasForm({"origem": "scpi"})
    assert vazio.is_valid() and not vazio.cleaned_data["desde"] and not vazio.cleaned_data["ate"]


def test_periodo_inicial_das_saidas_e_o_padrao_do_comando():
    Importacao.objects.create(
        tipo="SAIDAS",
        situacao="SUCESSO",
        fim=timezone.now(),
        periodo_de=date(2026, 9, 1),
        periodo_ate=date(2026, 10, 3),
    )
    form = RoboSaidasForm()
    assert form.initial["desde"] == date(2026, 9, 26)
    assert form.initial["ate"] == timezone.localdate()


def test_lancamento_exige_lotes_da_fila_atual():
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    assert LancamentoForm({"modo": "simular"}).errors["lotes"]
    assert (
        "não está mais na fila"
        in LancamentoForm({"modo": "simular", "lotes": ["P-9"]}).errors["lotes"][0]
    )
    ok = LancamentoForm({"modo": "simular", "lotes": [p.numero]})
    assert ok.is_valid() and ok.cleaned_data["lotes"] == [p.numero]
    assert LancamentoForm({"modo": "outro", "lotes": [p.numero]}).errors["modo"]


def test_formulario_do_lancamento_aceita_o_formato_antigo_dos_botoes():
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    antigo = LancamentoForm.da_requisicao({"simulacao": "1", "lotes": [p.numero]})
    assert antigo.is_valid() and antigo.cleaned_data["modo"] == "simular"
    padrao = LancamentoForm.da_requisicao({"lotes": [p.numero]})
    assert padrao.is_valid() and padrao.cleaned_data["modo"] == "lancar"


# ---- disparo -----------------------------------------------------------------------------------


def argumentos(chamada):
    return chamada[2:]  # sem o python e o manage.py


def test_disparo_do_cadastro_com_e_sem_forcar(processos):
    assert iniciar_importacao("cadastro") is True
    assert iniciar_importacao("cadastro", forcar=True) is True
    assert argumentos(processos[0]) == ["importar_cadastro"]
    assert argumentos(processos[1]) == ["importar_cadastro", "--forcar"]


def test_disparo_das_saidas_leva_o_periodo(processos):
    iniciar_importacao("saidas", desde=date(2026, 10, 1), ate=date(2026, 10, 12))
    assert argumentos(processos[0]) == [
        "importar_saidas_scpi",
        "--desde",
        "01/10/2026",
        "--ate",
        "12/10/2026",
    ]
    iniciar_importacao("saidas")
    assert argumentos(processos[1]) == ["importar_saidas_scpi"]


def test_disparo_com_csv_usa_arquivo_e_manda_apagar(processos, tmp_path):
    iniciar_importacao("estoque", arquivo=tmp_path / "x.csv")
    assert argumentos(processos[0]) == [
        "importar_estoque",
        "--arquivo",
        str(tmp_path / "x.csv"),
        "--apagar-arquivo",
    ]


def test_cada_robo_tem_o_seu_log(processos, tmp_path):
    for tipo in ("cadastro", "estoque", "saidas"):
        iniciar_importacao(tipo)
        assert (tmp_path / f"importar_{tipo}.log").exists()


def test_disparo_recusa_com_importacao_em_andamento(processos):
    Importacao.objects.create(tipo="ESTOQUE")
    assert iniciar_importacao("cadastro") is False
    assert processos == []


def test_csv_enviado_fica_na_pasta_de_uploads(settings, tmp_path):
    settings.LOG_DIR = tmp_path
    caminho = guardar_csv_enviado(csv(conteudo=b"a;b\n1;2\n"))
    assert caminho.parent == tmp_path / "uploads" and caminho.suffix == ".csv"
    assert caminho.read_bytes() == b"a;b\n1;2\n"


def test_lancamento_passa_cada_lote_ao_robo(processos):
    usuario = get_user_model().objects.create_user(username="99")
    iniciar_lancamento(usuario, simulacao=True, lotes=["P-0001", "AV-0002"])
    assert argumentos(processos[0])[-5:] == ["--dry-run", "--lote", "P-0001", "--lote", "AV-0002"]
    assert "--limite" not in processos[0]


# ---- comandos: o CSV enviado é apagado ao fim --------------------------------------------------


def test_comando_apaga_o_csv_enviado_ao_terminar(tmp_path):
    copia = tmp_path / "estoque.csv"
    shutil.copy(FIXTURES / "estoque.csv", copia)
    call_command("importar_estoque", arquivo=str(copia), apagar_arquivo=True)
    assert not copia.exists()


def test_comando_apaga_o_csv_enviado_mesmo_se_a_importacao_falhar(tmp_path):
    copia = tmp_path / "lixo.csv"
    copia.write_bytes(b"isto nao e um relatorio\n")
    with pytest.raises(CommandError):
        call_command("importar_estoque", arquivo=str(copia), apagar_arquivo=True)
    assert not copia.exists()


def test_comando_sem_apagar_mantem_o_arquivo(tmp_path):
    copia = tmp_path / "estoque.csv"
    shutil.copy(FIXTURES / "estoque.csv", copia)
    call_command("importar_estoque", arquivo=str(copia))
    assert copia.exists()


# ---- páginas -----------------------------------------------------------------------------------


def test_automacoes_tem_uma_aba_por_robo(client, usuario_logado):
    texto = client.get(reverse("automacoes:pagina")).text
    assert re.findall(r'role="tab"[^>]*data-aba="([\w-]+)"', texto) == [
        "visao-geral",
        "lancamento",
        "cadastro",
        "estoque",
        "saidas",
    ]
    for robo in ("cadastro", "estoque", "saidas"):
        assert f'action="{reverse("automacoes:importar", args=[robo])}"' in texto
    ids = re.findall(r'\sid="([^"]+)"', texto)
    assert len(ids) == len(set(ids))  # os três formulários não repetem ids


def test_aba_ativa_vem_da_url(client, usuario_logado):
    texto = client.get(reverse("automacoes:pagina"), {"aba": "estoque"}).text
    assert re.search(r'id="aba-estoque"[^>]*aria-selected="true"', texto)
    padrao = client.get(reverse("automacoes:pagina"), {"aba": "invalida"}).text
    assert re.search(r'id="aba-visao-geral"[^>]*aria-selected="true"', padrao)


def test_aba_das_saidas_ja_vem_com_o_periodo_padrao(client, usuario_logado):
    texto = client.get(reverse("automacoes:pagina")).text
    assert re.search(r'name="desde"[^>]*value="[0-9]{4}-[0-9]{2}-[0-9]{2}"', texto)


def test_importar_exige_login_e_post(client, usuario_logado):
    assert client.get(reverse("automacoes:importar", args=["estoque"])).status_code == 405
    client.logout()
    r = client.post(reverse("automacoes:importar", args=["estoque"]), {"origem": "scpi"})
    assert r.status_code == 302 and r.url.startswith(reverse("login"))


def test_robo_desconhecido_da_404(client, usuario_logado):
    assert client.post(reverse("automacoes:importar", args=["lixo"])).status_code == 404


def test_importar_saidas_envia_o_periodo_escolhido(client, usuario_logado, processos):
    client.post(
        reverse("automacoes:importar", args=["saidas"]),
        {"origem": "scpi", "desde": "2026-10-01", "ate": "2026-10-10"},
    )
    assert argumentos(processos[0])[-4:] == ["--desde", "01/10/2026", "--ate", "10/10/2026"]


def test_importar_com_csv_grava_o_arquivo_e_o_passa_ao_comando(
    client, usuario_logado, processos, tmp_path
):
    client.post(
        reverse("automacoes:importar", args=["estoque"]),
        {"origem": "csv", "arquivo": csv(conteudo=b"x;y\n")},
    )
    args = argumentos(processos[0])
    assert (
        args[0] == "importar_estoque" and args[1] == "--arquivo" and args[-1] == "--apagar-arquivo"
    )
    assert Path(args[2]).parent == tmp_path / "uploads" and Path(args[2]).read_bytes() == b"x;y\n"


def test_envio_invalido_mostra_o_erro_na_aba_e_nao_roda(client, usuario_logado, processos):
    r = client.post(reverse("automacoes:importar", args=["estoque"]), {"origem": "csv"})
    assert r.status_code == 200 and processos == []
    assert "Escolha o arquivo CSV." in r.text
    assert re.search(r'id="aba-estoque"[^>]*aria-selected="true"', r.text)


def test_importar_com_outra_importacao_em_andamento_avisa_e_nao_roda(
    client, usuario_logado, processos
):
    Importacao.objects.create(tipo="CADASTRO")
    r = client.post(
        reverse("automacoes:importar", args=["estoque"]), {"origem": "scpi"}, follow=True
    )
    assert processos == [] and "Já há uma importação em andamento" in r.text


def test_csv_enviado_e_descartado_se_o_robo_recusa_depois_de_guardar(
    client, usuario_logado, processos, tmp_path, monkeypatch
):
    # A corrida: a checagem da página passou, mas outra importação começou antes do disparo.
    monkeypatch.setattr("automacoes.views.iniciar_importacao", lambda *a, **k: False)
    client.post(
        reverse("automacoes:importar", args=["estoque"]),
        {"origem": "csv", "arquivo": csv()},
    )
    assert list((tmp_path / "uploads").glob("*")) == []


def test_csv_enviado_e_descartado_se_o_disparo_quebra(
    client, usuario_logado, processos, tmp_path, monkeypatch
):
    def quebra(*a, **k):
        raise RuntimeError("não subiu")

    monkeypatch.setattr("automacoes.views.iniciar_importacao", quebra)
    client.raise_request_exception = False
    r = client.post(
        reverse("automacoes:importar", args=["estoque"]),
        {"origem": "csv", "arquivo": csv()},
    )
    assert r.status_code == 500
    assert list((tmp_path / "uploads").glob("*")) == []


def test_botoes_dos_robos_ficam_desabilitados_com_importacao_em_andamento(client, usuario_logado):
    Importacao.objects.create(tipo="CADASTRO")
    texto = client.get(reverse("automacoes:pagina")).text
    assert len(re.findall(r"<button[^>]*data-robo-rodar[^>]*disabled", texto)) == 3
    assert 'data-em-andamento="1"' in texto


def test_pagina_de_lancamentos_tem_o_modo_nos_botoes_e_as_caixas_de_marcar(client, usuario_logado):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    texto = client.get(LANCAMENTOS).text
    assert "Executar com opções" not in texto
    assert 'name="modo" value="simular"' in texto and 'name="lotes"' in texto
    assert 'name="limite"' not in texto


def test_lancar_com_modo_e_lotes(client, usuario_logado, monkeypatch):
    p = criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    chamadas = []
    monkeypatch.setattr(
        "automacoes.views.iniciar_lancamento",
        lambda u, simulacao, lotes: chamadas.append((simulacao, lotes)) or object(),
    )
    r = client.post(
        reverse("automacoes:lancar"), {"modo": "simular", "lotes": [p.numero]}, follow=True
    )
    assert chamadas == [(True, [p.numero])] and f"{p.numero}." in r.text


def test_lancar_sem_lotes_nao_inicia(client, usuario_logado, monkeypatch):
    criar_pedido(atendido=True, linhas=[("PENDENTE", "")])
    monkeypatch.setattr(
        "automacoes.views.iniciar_lancamento",
        lambda *a, **k: pytest.fail("não deveria iniciar"),
    )
    r = client.post(reverse("automacoes:lancar"), {"modo": "simular"}, follow=True)
    assert r.status_code == 200 and "Simulação iniciada" not in r.text


# ---- cadastro por período ----------------------------------------------------------------------


def test_disparo_do_cadastro_leva_o_periodo(processos):
    iniciar_importacao("cadastro", desde=date(2024, 1, 1), ate=date(2024, 12, 31))
    assert argumentos(processos[0]) == [
        "importar_cadastro",
        "--desde",
        "01/01/2024",
        "--ate",
        "31/12/2024",
    ]


def painel_do_cadastro(client):
    texto = client.get(reverse("automacoes:pagina"), {"aba": "cadastro"}).text
    return texto[texto.index('id="painel-cadastro"') : texto.index('id="painel-estoque"')]


def test_disparo_da_recarga_completa_leva_completo_e_forcar(processos):
    iniciar_importacao("cadastro", completo=True)
    iniciar_importacao("cadastro", completo=True, forcar=True)
    assert argumentos(processos[0]) == ["importar_cadastro", "--completo"]
    assert argumentos(processos[1]) == ["importar_cadastro", "--completo", "--forcar"]


# ---- cadastro: só os novos ou recarga completa --------------------------------------------------


def carga_de_cadastro(**campos):
    return Importacao.objects.create(
        tipo="CADASTRO", situacao="SUCESSO", fim=timezone.now(), **campos
    )


def material_visivel(codigo="900.001"):
    return Material.objects.create(codigo=codigo, nome="Parafuso")


def test_cadastro_sem_carga_so_aceita_a_recarga_completa():
    form = RoboCadastroForm({"origem": "scpi", "modo": "novos"})
    assert form.errors["modo"] == ["Ainda não há carga de cadastro: faça a recarga completa."]
    sem_modo = RoboCadastroForm({"origem": "scpi"})
    assert sem_modo.is_valid() and sem_modo.cleaned_data["completo"] is True
    assert RoboCadastroForm().fields["modo"].initial == "completo"


def test_cadastro_com_carga_o_padrao_e_so_os_novos():
    carga_de_cadastro(periodo_ate=date(2024, 6, 30))
    form = RoboCadastroForm({"origem": "scpi"})
    assert form.is_valid() and form.cleaned_data["completo"] is False
    assert form.padrao == (date(2024, 6, 23), timezone.localdate())
    assert RoboCadastroForm().fields["modo"].initial == "novos"
    completo = RoboCadastroForm({"origem": "scpi", "modo": "completo"})
    assert completo.is_valid() and completo.cleaned_data["completo"] is True


def test_csv_enviado_e_sempre_recarga_completa():
    carga_de_cadastro(periodo_ate=date(2024, 6, 30))
    arquivo = SimpleUploadedFile("cadastro.csv", b"CADPRO")
    form = RoboCadastroForm({"origem": "csv", "modo": "novos"}, {"arquivo": arquivo})
    assert form.is_valid() and form.cleaned_data["completo"] is True


def test_forcar_so_vale_na_recarga_completa_e_com_material_visivel():
    def forcar(modo):
        form = RoboCadastroForm({"origem": "scpi", "modo": modo, "forcar": "on"})
        assert form.is_valid()
        return form.cleaned_data["forcar"]

    assert forcar("completo") is False  # catálogo vazio: nada a ocultar
    material_visivel()
    assert forcar("completo") is True
    carga_de_cadastro(periodo_ate=date(2024, 6, 30))
    assert forcar("novos") is False


def test_material_oculto_nao_conta_como_visivel():
    Material.objects.create(codigo="900.002", nome="Oculto", oculto=True)
    assert RoboCadastroForm().visiveis == 0
    material_visivel()
    assert RoboCadastroForm().visiveis == 1


def test_aba_do_cadastro_sem_carga_orienta_a_carga_inicial(client, usuario_logado):
    painel = painel_do_cadastro(client)
    assert 'name="desde"' not in painel and 'name="completo"' not in painel
    assert "confirmar" not in painel
    assert "Ainda não há carga" in painel and 'data-sem-carga="1"' in painel
    assert "Disponível depois da primeira carga." in painel
    assert re.search(r'value="completo"[^>]*checked', painel)
    assert "data-robo-risco" not in painel  # catálogo vazio: nada a ocultar


def test_aba_do_cadastro_sem_carga_mas_com_materiais_avisa_do_forcar(client, usuario_logado):
    material_visivel()
    painel = painel_do_cadastro(client)
    assert 'data-sem-carga="1"' in painel and "data-robo-risco" in painel
    assert "Hoje há 1 material visível." in painel


def test_aba_do_cadastro_depois_da_carga_oferece_os_novos(client, usuario_logado):
    carga_de_cadastro(periodo_de=date(2024, 1, 1), periodo_ate=date(2024, 6, 30))
    for i in range(3):
        material_visivel(f"900.00{i}")
    painel = painel_do_cadastro(client)
    assert "Última carga que deu certo:" in painel and "só os novos" in painel
    assert "Cadastros novos desde 23/06/2024" in painel
    assert "data-sem-carga" not in painel
    assert re.search(r'value="novos"[^>]*checked', painel)
    assert "Hoje há 3 materiais visíveis." in painel


def test_importar_cadastro_recarga_completa_com_forcar_inicia_o_robo(
    client, usuario_logado, processos
):
    material_visivel()
    r = client.post(
        reverse("automacoes:importar", args=["cadastro"]),
        {"origem": "scpi", "modo": "completo", "forcar": "on"},
        follow=True,
    )
    assert argumentos(processos[0]) == ["importar_cadastro", "--completo", "--forcar"]
    assert "Importação de cadastro iniciada" in r.text


def test_importar_so_os_novos_deixa_o_periodo_para_o_comando(client, usuario_logado, processos):
    carga_de_cadastro(periodo_ate=date(2024, 6, 30))
    client.post(
        reverse("automacoes:importar", args=["cadastro"]), {"origem": "scpi", "modo": "novos"}
    )
    assert argumentos(processos[0]) == ["importar_cadastro"]


def test_importar_cadastro_por_csv_vira_recarga_completa(client, usuario_logado, processos):
    carga_de_cadastro(periodo_ate=date(2024, 6, 30))
    client.post(
        reverse("automacoes:importar", args=["cadastro"]),
        {
            "origem": "csv",
            "modo": "novos",
            "arquivo": SimpleUploadedFile("cadastro.csv", b"CADPRO"),
        },
    )
    args = argumentos(processos[0])
    assert args[:2] == ["importar_cadastro", "--completo"]
    assert "--arquivo" in args and args[-1] == "--apagar-arquivo"


def test_importar_so_os_novos_sem_carga_e_recusado(client, usuario_logado, processos):
    r = client.post(
        reverse("automacoes:importar", args=["cadastro"]),
        {"origem": "scpi", "modo": "novos"},
    )
    assert processos == []
    assert "faça a recarga completa" in r.text
