"""Sessão do SCPI compartilhada entre relatórios, com uma sessão falsa (sem navegador)."""

import os

import pytest
from django.core.management import call_command

from scpi import relatorios


class SessaoFalsa:
    abertas: list["SessaoFalsa"] = []

    def __init__(self, perfil):
        self.perfil = perfil
        self.fechada = False
        SessaoFalsa.abertas.append(self)

    def fechar(self):
        self.fechada = True


@pytest.fixture(autouse=True)
def sessao_falsa(monkeypatch):
    SessaoFalsa.abertas = []
    monkeypatch.setattr(relatorios, "_Sessao", SessaoFalsa)


def usar(perfil):
    with relatorios._sessao(perfil) as sessao:
        return sessao


def test_fora_do_bloco_cada_relatorio_abre_e_fecha_a_sua():
    a, b = usar("cadastro"), usar("estoque")
    assert a is not b
    assert (a.perfil, b.perfil) == ("cadastro", "estoque")
    assert a.fechada and b.fechada


def test_no_bloco_os_relatorios_dividem_uma_sessao_fechada_no_fim():
    with relatorios.sessao_compartilhada():
        a, b = usar("cadastro"), usar("estoque")
        assert a is b and not a.fechada
    assert a.fechada
    assert [s.perfil for s in SessaoFalsa.abertas] == ["catalogo"]


def test_bloco_sem_relatorio_baixado_nao_abre_o_navegador():
    with relatorios.sessao_compartilhada():
        pass
    assert SessaoFalsa.abertas == []


def test_relatorio_que_falha_descarta_a_sessao_e_o_seguinte_abre_outra():
    with relatorios.sessao_compartilhada():
        with pytest.raises(RuntimeError), relatorios._sessao("cadastro") as primeira:
            raise RuntimeError("tela inesperada")
        assert primeira.fechada
        segunda = usar("estoque")
        assert segunda is not primeira and not segunda.fechada
    assert segunda.fechada


def test_depois_do_bloco_volta_a_uma_sessao_por_relatorio():
    with relatorios.sessao_compartilhada():
        usar("cadastro")
    avulsa = usar("estoque")
    assert avulsa.perfil == "estoque" and avulsa.fechada


def test_atualizar_catalogo_baixa_os_quatro_na_mesma_sessao(monkeypatch):
    usadas = []

    def comando(nome, *args, **kwargs):
        usadas.append(usar(nome))

    monkeypatch.setattr("scpi.management.commands.atualizar_catalogo.call_command", comando)
    call_command("atualizar_catalogo")
    # Cadastro, estoque, saídas e, por último, as requisições da conciliação (spec 010, R19).
    assert len(usadas) == 4 and all(sessao is usadas[0] for sessao in usadas)
    assert usadas[0].fechada


def test_orm_liberado_so_enquanto_a_sessao_compartilhada_existe(monkeypatch):
    # Com a sessão aberta, a API síncrona do Playwright mantém um laço asyncio na thread, e o
    # Django recusaria as gravações das importações (SynchronousOnlyOperation).
    monkeypatch.delenv("DJANGO_ALLOW_ASYNC_UNSAFE", raising=False)
    with relatorios.sessao_compartilhada():
        assert os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] == "true"
    assert "DJANGO_ALLOW_ASYNC_UNSAFE" not in os.environ


def test_orm_volta_ao_que_era_mesmo_se_algo_falha(monkeypatch):
    monkeypatch.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "valor-anterior")
    with pytest.raises(RuntimeError), relatorios.sessao_compartilhada():
        usar("cadastro")
        raise RuntimeError
    assert os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] == "valor-anterior"
