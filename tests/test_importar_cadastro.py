from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from catalogo.models import Importacao, Material
from scpi import relatorios

pytestmark = pytest.mark.django_db
FIX = Path(__file__).parent / "fixtures" / "scpi"
CABECALHO = "CADPRO;DISC1;UNID1;NOMEGRUPO;NOMESUBGRUPO;NOCULTAR;GRUPO\r\n"


def importar(**opcoes):
    call_command("importar_cadastro", arquivo=FIX / "cadastro.csv", **opcoes)


def test_importa_o_cadastro():
    importar()
    assert Material.objects.count() == 4
    m = Material.objects.get(codigo="001.001.001")
    assert (m.nome, m.unidade, m.grupo, m.subgrupo, m.oculto, m.duplicado) == (
        "DETERGENTE NEUTRO 500 ML",
        "UN",
        "MATERIAL DE LIMPEZA",
        "PRODUTOS DE LIMPEZA",
        False,
        False,
    )
    assert Material.objects.get(codigo="001.001.002").oculto
    luva = Material.objects.get(codigo="013.005.007")
    assert luva.duplicado and luva.nome == "LUVA NITRÍLICA"
    assert Material.objects.filter(codigo="017.004").exists()
    imp = Importacao.objects.get()
    assert (imp.tipo, imp.situacao, imp.linhas) == ("CADASTRO", "SUCESSO", 4)
    assert imp.avisos == [
        "Linhas sem código ou nome ignoradas: 1.",
        "Códigos repetidos no cadastro (bloqueados): 013.005.007.",
    ]


def test_saida_do_comando_resume(capsys):
    importar()
    saida = capsys.readouterr().out
    assert "Cadastro: 4 materiais gravados." in saida
    assert "Códigos repetidos no cadastro (bloqueados): 013.005.007." in saida


def test_atualiza_material_existente_sem_mexer_no_estoque():
    agora = timezone.now()
    Material.objects.create(
        codigo="001.001.001", nome="ANTIGO", unidade="CX", estoque=3, estoque_em=agora
    )
    importar()
    m = Material.objects.get(codigo="001.001.001")
    assert (m.nome, m.unidade, m.estoque, m.estoque_em) == (
        "DETERGENTE NEUTRO 500 ML",
        "UN",
        3,
        agora,
    )


def test_material_que_sumiu_fica_oculto_e_mantem_o_estoque():
    sumido = Material.objects.create(codigo="555.000.001", nome="ANTIGO", estoque=7)
    importar(forcar=True)  # 1 de 1 visível sumiria: acima do limite de 20%
    sumido.refresh_from_db()
    assert sumido.oculto and sumido.estoque == 7


def test_reaparecer_desoculta_e_deixa_de_ser_duplicado():
    Material.objects.create(codigo="017.004", nome="X", oculto=True, duplicado=True)
    importar()
    m = Material.objects.get(codigo="017.004")
    assert (m.nome, m.oculto, m.duplicado) == ("MATERIAL LEGADO", False, False)


def test_cadastro_truncado_aborta_sem_esconder_nada():
    for n in range(10):
        Material.objects.create(codigo=f"900.000.{n:03}", nome=f"M{n}")
    with pytest.raises(CommandError, match=r"não traz 10 dos 10 materiais visíveis"):
        importar()
    assert not Material.objects.filter(oculto=True).exists()
    assert Material.objects.count() == 10
    assert Importacao.objects.get().situacao == "FALHA"


def test_sumir_ate_vinte_por_cento_nao_aborta():
    for codigo in ["001.001.001", "001.001.002", "013.005.007", "017.004", "900.000.000"]:
        Material.objects.create(codigo=codigo, nome=codigo)
    importar()  # 1 de 5 visíveis some: exatamente 20%
    assert Material.objects.get(codigo="900.000.000").oculto


def test_sumir_mais_de_vinte_por_cento_aborta():
    for codigo in ["001.001.001", "013.005.007", "017.004", "900.000.000"]:
        Material.objects.create(codigo=codigo, nome=codigo)
    with pytest.raises(CommandError, match=r"não traz 1 dos 4 materiais visíveis"):
        importar()  # 1 de 4: 25%


def test_forcar_aceita_o_cadastro_menor():
    Material.objects.create(codigo="900.000.001", nome="M")
    importar(forcar=True)
    assert Material.objects.get(codigo="900.000.001").oculto


def test_cadastro_vazio_aborta(tmp_path):
    vazio = tmp_path / "vazio.csv"
    vazio.write_bytes((FIX / "cadastro.csv").read_bytes().splitlines(keepends=True)[0])
    with pytest.raises(CommandError, match="não tem nenhum material"):
        call_command("importar_cadastro", arquivo=vazio)


def test_texto_longo_e_cortado_com_aviso(tmp_path):
    arquivo = tmp_path / "longo.csv"
    arquivo.write_bytes(
        (CABECALHO + f"001.001.001;{'A' * 300};{'U' * 25};G;S;Não\r\n").encode("utf-8-sig")
    )
    call_command("importar_cadastro", arquivo=arquivo)
    m = Material.objects.get()
    assert len(m.nome) == 255 and len(m.unidade) == 20
    assert Importacao.objects.get().avisos == [
        "Texto cortado em nome (255 caracteres): 001.001.001.",
        "Texto cortado em unidade (20 caracteres): 001.001.001.",
    ]


def test_sem_arquivo_baixa_do_scpi(monkeypatch):
    chamadas = []

    def baixar(de, ate):
        chamadas.append((de, ate))
        return [(FIX / "cadastro.csv").read_bytes()]

    monkeypatch.setattr(relatorios, "baixar_cadastro", baixar)
    call_command("importar_cadastro")
    assert chamadas == [(date(2000, 1, 1), timezone.localdate())]
    assert Material.objects.count() == 4


def test_importacao_em_andamento_recusa(monkeypatch, caplog):
    from scpi import execucao

    def ocupado(*args, **kwargs):
        raise execucao.ImportacaoEmAndamento("CADASTRO")

    monkeypatch.setattr(execucao, "executar", ocupado)
    with pytest.raises(CommandError, match=r"^Importação de cadastro já em andamento\.$"):
        importar()
    assert any(r.name == "scpi" and "já em andamento" in r.getMessage() for r in caplog.records)


def test_codigo_igual_para_o_banco_atualiza_em_vez_de_duplicar(tmp_path):
    """A collation do MySQL não distingue maiúsculas: '0-a' e '0-A' são o mesmo código."""
    Material.objects.create(codigo="000.009.0-a", nome="ANTIGO")
    arquivo = tmp_path / "c.csv"
    arquivo.write_bytes((CABECALHO + "000.009.0-A;NOVO;UN;G;S;Não\r\n").encode("utf-8-sig"))
    call_command("importar_cadastro", arquivo=arquivo)
    assert Material.objects.get().nome == "NOVO"


def test_periodo_acha_o_material_pela_mesma_chave_do_codigo_com_espacos_internos(tmp_path):
    """`chave()` colapsa espaços internos, a collation do banco não: '000.009.0  A' e
    '000.009.0 A' são o mesmo material para a importação, parcial ou completa, e não viram dois.
    Só o CSV salvo por uma planilha (separado por vírgula) aceita espaço no meio do código."""
    Material.objects.create(codigo="000.009.0  A", nome="ANTIGO")
    arquivo = tmp_path / "c.csv"
    planilha = CABECALHO.replace(";", ",") + "000.009.0 A,NOVO,UN,G,S,Não,001\r\n"
    arquivo.write_bytes(planilha.encode("utf-8-sig"))
    call_command("importar_cadastro", arquivo=arquivo, desde="01/01/2024")
    assert Material.objects.count() == 1 and Material.objects.get().nome == "NOVO"


# ---- importação parcial (--desde / --ate): grava o que o CSV traz e não oculta ninguém ----------


def test_periodo_grava_so_o_que_o_csv_traz_e_nao_oculta_nem_aborta():
    for n in range(10):
        Material.objects.create(codigo=f"900.000.{n:03}", nome=f"M{n}")
    importar(desde="01/01/2024")  # completo, isto abortaria: o CSV não traz os 10 visíveis
    assert not Material.objects.filter(oculto=True, codigo__startswith="900.").exists()
    assert Material.objects.count() == 10 + 4
    imp = Importacao.objects.get()
    assert imp.situacao == "SUCESSO" and imp.periodo_de == date(2024, 1, 1)
    assert imp.periodo_ate == timezone.localdate()


def test_periodo_atualiza_o_que_o_csv_traz():
    Material.objects.create(codigo="001.001.001", nome="ANTIGO", estoque=5)
    importar(ate="31/12/2024")
    m = Material.objects.get(codigo="001.001.001")
    assert m.nome == "DETERGENTE NEUTRO 500 ML" and m.estoque == 5


def test_periodo_vai_ao_relatorio_do_scpi(monkeypatch):
    chamadas = []

    def baixar(de, ate):
        chamadas.append((de, ate))
        return [(FIX / "cadastro.csv").read_bytes()]

    monkeypatch.setattr(relatorios, "baixar_cadastro", baixar)
    call_command("importar_cadastro", desde="01/01/2024", ate="31/12/2024")
    assert chamadas == [(date(2024, 1, 1), date(2024, 12, 31))]
    call_command("importar_cadastro", desde="01/06/2025")
    assert chamadas[-1] == (date(2025, 6, 1), timezone.localdate())


def test_sem_periodo_segue_completo_e_sem_periodo_registrado(monkeypatch):
    importar()
    imp = Importacao.objects.get()
    assert imp.periodo_de is None and imp.periodo_ate is None


def test_periodo_nao_combina_com_forcar():
    with pytest.raises(CommandError, match=r"--forcar não se aplica a um período"):
        importar(desde="01/01/2024", forcar=True)
    assert not Material.objects.exists()


def test_periodo_invertido_ou_no_futuro_e_recusado():
    with pytest.raises(CommandError, match="é depois do fim"):
        importar(desde="10/10/2026", ate="01/10/2026")
    with pytest.raises(CommandError, match="é no futuro"):
        importar(ate="01/01/2999")
    with pytest.raises(CommandError, match="dd/mm/aaaa"):
        importar(desde="amanhã")
    assert not Material.objects.exists()


def test_resumo_da_importacao_parcial(capsys):
    importar(desde="01/01/2024", ate="31/12/2024")
    assert (
        "Cadastro parcial (01/01/2024 a 31/12/2024): 4 materiais gravados; nenhum foi ocultado."
        in (capsys.readouterr().out)
    )


# ---- depois da primeira carga, o padrão é incremental (só os cadastros novos) --------------------


def carga_anterior(periodo_ate=None, situacao="SUCESSO"):
    return Importacao.objects.create(
        tipo="CADASTRO", situacao=situacao, fim=timezone.now(), periodo_ate=periodo_ate
    )


def baixar_registrando(monkeypatch):
    chamadas = []

    def baixar(de, ate):
        chamadas.append((de, ate))
        return [(FIX / "cadastro.csv").read_bytes()]

    monkeypatch.setattr(relatorios, "baixar_cadastro", baixar)
    return chamadas


def test_sem_carga_anterior_nao_ha_periodo_padrao():
    from scpi.gravacao import periodo_cadastro_padrao

    assert periodo_cadastro_padrao(timezone.localdate()) is None
    carga_anterior(situacao="FALHA")  # falha não conta como carga
    assert periodo_cadastro_padrao(timezone.localdate()) is None


def test_periodo_padrao_parte_do_corte_da_ultima_carga_com_sobreposicao():
    from scpi.gravacao import periodo_cadastro_padrao

    hoje = timezone.localdate()
    carga_anterior()  # completa: o corte é o dia em que terminou
    assert periodo_cadastro_padrao(hoje) == (hoje - timedelta(days=7), hoje)
    carga_anterior(periodo_ate=date(2024, 6, 30))  # parcial antiga não faz o corte recuar
    assert periodo_cadastro_padrao(hoje) == (hoje - timedelta(days=7), hoje)


def test_corte_de_carga_parcial_e_o_fim_do_seu_periodo():
    from scpi.gravacao import periodo_cadastro_padrao

    carga_anterior(periodo_ate=date(2024, 6, 30))
    assert periodo_cadastro_padrao(date(2026, 10, 12)) == (date(2024, 6, 23), date(2026, 10, 12))


def test_apos_a_primeira_carga_o_robo_pede_so_os_novos_e_nao_oculta_ninguem(monkeypatch):
    for n in range(10):
        Material.objects.create(codigo=f"900.000.{n:03}", nome=f"M{n}")
    carga_anterior(periodo_ate=date(2024, 6, 30))
    chamadas = baixar_registrando(monkeypatch)
    call_command("importar_cadastro")
    assert chamadas == [(date(2024, 6, 23), timezone.localdate())]
    # O completo abortaria (10 de 10 visíveis sumidos); o incremental não oculta nenhum deles.
    assert not Material.objects.filter(oculto=True, codigo__startswith="900.").exists()
    assert Material.objects.count() == 10 + 4


def test_incremental_registra_o_periodo_da_carga(monkeypatch):
    carga_anterior(periodo_ate=date(2024, 6, 30))
    baixar_registrando(monkeypatch)
    call_command("importar_cadastro")
    nova = Importacao.objects.filter(tipo="CADASTRO").order_by("-inicio").first()
    assert (nova.periodo_de, nova.periodo_ate) == (date(2024, 6, 23), timezone.localdate())


def test_completo_pede_o_cadastro_inteiro_mesmo_com_carga_anterior(monkeypatch):
    carga_anterior(periodo_ate=date(2024, 6, 30))
    chamadas = baixar_registrando(monkeypatch)
    call_command("importar_cadastro", completo=True)
    assert chamadas == [(date(2000, 1, 1), timezone.localdate())]


def test_forcar_sem_datas_tambem_e_recarga_completa(monkeypatch):
    carga_anterior(periodo_ate=date(2024, 6, 30))
    Material.objects.create(codigo="900.000.001", nome="M")
    chamadas = baixar_registrando(monkeypatch)
    call_command("importar_cadastro", forcar=True)
    assert chamadas == [(date(2000, 1, 1), timezone.localdate())]
    assert Material.objects.get(codigo="900.000.001").oculto  # completo: o que sumiu fica oculto


def test_csv_enviado_sem_datas_e_sempre_completo_mesmo_com_carga_anterior():
    carga_anterior(periodo_ate=date(2024, 6, 30))
    for codigo in ["001.001.001", "001.001.002", "013.005.007", "017.004", "900.000.000"]:
        Material.objects.create(codigo=codigo, nome=codigo)
    importar()  # --arquivo, sem datas: completo, então o que sumiu (1 de 5) fica oculto
    assert Material.objects.get(codigo="900.000.000").oculto


def test_completo_nao_combina_com_periodo():
    with pytest.raises(CommandError, match=r"--completo não se aplica a um período"):
        importar(desde="01/01/2024", completo=True)


def test_resumo_do_incremental_automatico(capsys, monkeypatch):
    carga_anterior(periodo_ate=date(2024, 6, 30))
    baixar_registrando(monkeypatch)
    call_command("importar_cadastro")
    assert "(novos desde a última carga)" in capsys.readouterr().out


def test_so_os_novos_sem_nenhum_material_novo_e_sucesso(monkeypatch, capsys):
    # Semana sem cadastro novo: o SCPI responde "Nada a exibir" para todos os tipos.
    Material.objects.create(codigo="001.001.001", nome="ANTIGO")
    carga_anterior(periodo_ate=date(2024, 6, 30))
    monkeypatch.setattr(relatorios, "baixar_cadastro", lambda de, ate: [])
    call_command("importar_cadastro")
    nova = Importacao.objects.filter(tipo="CADASTRO").order_by("-inicio").first()
    assert (nova.situacao, nova.linhas) == ("SUCESSO", 0)
    assert "0 materiais gravados" in capsys.readouterr().out
    assert not Material.objects.get(codigo="001.001.001").oculto


def test_recarga_completa_sem_nenhum_material_aborta(monkeypatch):
    Material.objects.create(codigo="001.001.001", nome="ANTIGO")
    monkeypatch.setattr(relatorios, "baixar_cadastro", lambda de, ate: [])
    with pytest.raises(CommandError, match="não tem nenhum material"):
        call_command("importar_cadastro", completo=True)
    assert not Material.objects.get(codigo="001.001.001").oculto
