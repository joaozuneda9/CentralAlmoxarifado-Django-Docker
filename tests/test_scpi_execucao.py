from datetime import date

import pytest
from django.db import InterfaceError, OperationalError, connection, connections

from catalogo.models import Importacao, Material, trava_importacao
from scpi.execucao import ImportacaoEmAndamento, Resultado, executar, trava
from scpi.leitura import ErroImportacao

pytestmark = pytest.mark.django_db


def nada(conteudo):
    return Resultado(0, [])


def test_sucesso_registra_linhas_avisos_e_periodo():
    imp = executar(
        "SAIDAS",
        lambda: b"x",
        lambda c: Resultado(3, ["um aviso"]),
        periodo=(date(2026, 1, 1), date(2026, 1, 31)),
    )
    imp.refresh_from_db()
    assert (imp.situacao, imp.linhas, imp.avisos) == ("SUCESSO", 3, ["um aviso"])
    assert (imp.periodo_de, imp.periodo_ate) == (date(2026, 1, 1), date(2026, 1, 31))
    assert imp.fim is not None and imp.erro == ""


def test_gravar_recebe_o_conteudo_baixado():
    recebido = []
    executar("ESTOQUE", lambda: b"csv", lambda c: recebido.append(c) or Resultado(0, []))
    assert recebido == [b"csv"]


def test_falha_desfaz_o_que_foi_gravado_e_registra_o_erro():
    def gravar(conteudo):
        Material.objects.create(codigo="1", nome="X")
        raise ErroImportacao("Estoque: o CSV não tem nenhum material; nada foi alterado.")

    imp = executar("ESTOQUE", lambda: b"x", gravar)
    imp.refresh_from_db()
    assert imp.situacao == "FALHA" and imp.fim is not None
    assert imp.erro == "Estoque: o CSV não tem nenhum material; nada foi alterado."
    assert not Material.objects.exists()


def test_falha_ao_baixar_tambem_e_registrada():
    def baixar():
        raise RuntimeError("Nenhum CSV interceptado")

    imp = executar("SAIDAS", baixar, nada)
    assert imp.situacao == "FALHA"
    assert imp.erro == "Falha inesperada: Nenhum CSV interceptado"


def test_segunda_importacao_do_mesmo_tipo_e_recusada(trava_importacao_ocupada):
    trava_importacao_ocupada("ESTOQUE")
    with pytest.raises(ImportacaoEmAndamento):
        executar("ESTOQUE", lambda: pytest.fail("não deveria baixar"), nada)
    assert not Importacao.objects.exists()
    assert executar("CADASTRO", lambda: b"x", nada).situacao == "SUCESSO"


def test_trava_e_liberada_ao_terminar():
    executar("ESTOQUE", lambda: b"x", nada)
    outra = connections.create_connection("default")
    try:
        with outra.cursor() as c:
            c.execute("SELECT GET_LOCK(%s, 0)", [trava_importacao("ESTOQUE")])
            assert c.fetchone()[0] == 1
    finally:
        outra.close()


def test_trava_ocupada_entrega_falso():
    with trava("almoxarifado:teste") as primeira:
        outra = connections.create_connection("default")
        try:
            with outra.cursor() as c:
                c.execute("SELECT GET_LOCK('almoxarifado:teste', 0)")
                assert c.fetchone()[0] == 0
        finally:
            outra.close()
    assert primeira is True


def liberacao_quebrada(execute, sql, params, many, context):
    """`execute_wrapper` que simula o banco caindo bem na hora de liberar a trava."""
    if "RELEASE_LOCK" in sql:
        raise OperationalError("MySQL server has gone away")
    return execute(sql, params, many, context)


def test_falha_ao_liberar_a_trava_nao_esconde_a_excecao_de_dentro():
    try:
        with connection.execute_wrapper(liberacao_quebrada):
            with pytest.raises(ValueError, match="a de dentro"):
                with trava("almoxarifado:teste") as obtida:
                    assert obtida
                    raise ValueError("a de dentro")
    finally:
        with connection.cursor() as c:
            c.execute("SELECT RELEASE_LOCK('almoxarifado:teste')")


def test_conexao_perdida_ao_liberar_a_trava_nao_esconde_a_excecao_de_dentro():
    def fechada(execute, sql, params, many, context):
        if "RELEASE_LOCK" in sql:
            raise InterfaceError("(0, '')")
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(fechada):
            with pytest.raises(ValueError, match="a de dentro"):
                with trava("almoxarifado:teste") as obtida:
                    assert obtida
                    raise ValueError("a de dentro")
    finally:
        with connection.cursor() as c:
            c.execute("SELECT RELEASE_LOCK('almoxarifado:teste')")
