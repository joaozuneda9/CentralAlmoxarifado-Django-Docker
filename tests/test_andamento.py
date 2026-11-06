"""Apresentação de uma execução do robô (`pedidos/andamento.py`): funções puras, sem banco."""

from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from pedidos.andamento import (
    acompanhamento,
    contadores,
    duracao,
    estimativa,
    etapa_do_log,
    explicar_falha,
    feitas,
    frase,
    momento,
    n_de_m,
    precisa_conferir,
    ultima_atividade,
)
from pedidos.models import ExecucaoRobo
from scpi.lancamento import LANCAMENTO_BLOQUEADO

# 14/10/2026 13:25 no horário de Brasília (UTC-3).
AGORA = timezone.make_aware(datetime(2026, 10, 14, 13, 25))


def execucao(**campos):
    campos.setdefault("inicio", AGORA)
    return ExecucaoRobo(**campos)


def test_feitas_conta_simuladas_na_simulacao_e_lancadas_no_real():
    resumo = {"requisicoes": 3, "simuladas": 3, "lancadas": 1}
    assert feitas(execucao(simulacao=True, resumo=resumo)) == 3
    assert feitas(execucao(simulacao=False, resumo=resumo)) == 1
    assert feitas(execucao(simulacao=True, resumo={})) == 0


def test_n_de_m():
    simulada = execucao(simulacao=True, resumo={"requisicoes": 3, "simuladas": 3})
    assert n_de_m(simulada) == "3 de 3 requisições"
    assert n_de_m(execucao(resumo={"requisicoes": 3, "lancadas": 2})) == "2 de 3 requisições"
    assert n_de_m(execucao(resumo={"requisicoes": 1, "lancadas": 1})) == "1 de 1 requisição"


def test_n_de_m_nunca_mostra_zero_de_zero():
    assert n_de_m(execucao(resumo={})) is None
    assert n_de_m(execucao(resumo={"requisicoes": 0, "ignoradas": 2})) is None


def test_duracao():
    assert duracao(AGORA, None) == "—"
    assert duracao(AGORA, AGORA + timedelta(seconds=45)) == "45 s"
    assert duracao(AGORA, AGORA + timedelta(minutes=2, seconds=5)) == "2 min 5 s"
    assert duracao(AGORA, AGORA + timedelta(minutes=2)) == "2 min"
    assert duracao(AGORA, AGORA + timedelta(hours=1, minutes=3, seconds=20)) == "1 h 3 min"
    assert duracao(AGORA, AGORA) == "0 s"


def test_momento_em_hora_local():
    assert momento(AGORA, AGORA) == "hoje, 13:25"
    assert momento(AGORA - timedelta(days=1), AGORA) == "ontem, 13:25"
    assert momento(AGORA - timedelta(days=7), AGORA) == "07/10, 13:25"


def test_momento_usa_o_dia_local_e_nao_o_utc():
    # 22:30 de 13/10 em Brasília já é 01:30 de 14/10 em UTC: continua sendo "ontem".
    noite = timezone.make_aware(datetime(2026, 10, 13, 22, 30))
    assert momento(noite, AGORA) == "ontem, 22:30"


def falha(simulacao=True, erro="Falha inesperada: boom", log="10:00 → (1/3)\n", **resumo):
    return execucao(
        simulacao=simulacao, situacao="FALHA", fim=AGORA, erro=erro, log=log, resumo=resumo
    )


def test_sem_falha_nao_ha_explicacao():
    assert explicar_falha(execucao(situacao="SUCESSO")) is None


@pytest.mark.parametrize("erro", [LANCAMENTO_BLOQUEADO, "Outro lançamento já está em andamento."])
def test_erro_conhecido_vem_como_esta(erro):
    f = explicar_falha(falha(erro=erro, log=""))
    assert f.frase == erro and not f.tecnico


def test_falha_inesperada_vira_erro_do_sistema_com_detalhe_tecnico():
    f = explicar_falha(
        falha(
            erro="Falha inesperada: You cannot call this from an async context",
            requisicoes=3,
            processadas=1,
        )
    )
    assert f.frase == "O robô parou por um erro do sistema." and f.tecnico
    assert f.ate_onde == "Chegou a processar 1 de 3 requisições."


def test_timeout_vira_demora_do_scpi():
    f = explicar_falha(falha(erro="Falha inesperada: Timeout 30000ms exceeded.\nCall log: …"))
    assert f.frase == "O SCPI demorou demais para responder e o robô parou." and f.tecnico


def test_processo_que_nao_subiu_nao_chegou_a_iniciar():
    f = explicar_falha(falha(erro="[WinError 2] O sistema não pode encontrar o arquivo", log=""))
    assert f.frase == "O robô não chegou a iniciar." and f.tecnico
    assert f.ate_onde == "Parou antes de começar."


def test_frase_de_uma_linha_vem_como_esta_e_varias_linhas_sao_tecnicas():
    assert not explicar_falha(falha(erro="não foi possível travar o lote P-000001: x.")).tecnico
    f = explicar_falha(falha(erro="primeira linha\nsegunda linha"))
    assert f.frase == "primeira linha\nsegunda linha" and f.tecnico


def test_ate_onde_sem_total_parou_antes_de_comecar():
    assert explicar_falha(falha(requisicoes=0)).ate_onde == "Parou antes de começar."
    assert explicar_falha(falha(requisicoes=1, processadas=1)).ate_onde == (
        "Chegou a processar 1 de 1 requisição."
    )


def test_proximo_passo_depende_do_modo():
    simulacao = explicar_falha(falha(simulacao=True))
    assert "Nenhuma linha mudou de estado." in simulacao.proximo_passo
    assert "simular de novo" in simulacao.proximo_passo and simulacao.simular_de_novo
    real = explicar_falha(falha(simulacao=False))
    assert real.proximo_passo == "Confira as travas abaixo antes de lançar de novo."
    assert not real.simular_de_novo


def test_contadores_so_os_diferentes_de_zero_com_plural():
    assert contadores({}, simulacao=True) == []
    assert contadores({"requisicoes": 3, "processadas": 3, "simuladas": 3}, simulacao=True) == [
        "3 simuladas"
    ]
    assert contadores(
        {"requisicoes": 2, "lancadas": 1, "verificar": 1, "falhas": 2, "ignoradas": 1},
        simulacao=False,
    ) == ["1 lançada", "2 com erro", "1 para verificar", "1 deixada de fora"]


def test_precisa_conferir():
    assert precisa_conferir(execucao(resumo={"verificar": 1}))
    assert precisa_conferir(execucao(resumo={"falhas": 1}))
    assert precisa_conferir(falha(simulacao=False))
    assert not precisa_conferir(falha(simulacao=True))
    assert not precisa_conferir(execucao(situacao="SUCESSO", resumo={"lancadas": 2}))


def test_frase_concluida_e_com_pendencias():
    simulacao = execucao(
        simulacao=True, situacao="SUCESSO", fim=AGORA, resumo={"requisicoes": 3, "simuladas": 3}
    )
    assert frase(simulacao, AGORA, False) == (
        "Simulação de hoje, 13:25, concluída: 3 de 3 requisições preenchidas."
    )
    real = execucao(
        situacao="ATENCAO", fim=AGORA, resumo={"requisicoes": 2, "lancadas": 1, "verificar": 1}
    )
    assert frase(real, AGORA, False) == (
        "Lançamento de hoje, 13:25, concluído com pendências: 1 de 2 requisições lançadas."
    )
    uma = execucao(situacao="SUCESSO", fim=AGORA, resumo={"requisicoes": 1, "lancadas": 1})
    assert frase(uma, AGORA, False).endswith("1 de 1 requisição lançada.")


def test_frase_sem_nada_a_lancar():
    vazia = execucao(simulacao=True, situacao="SUCESSO", fim=AGORA, resumo={"requisicoes": 0})
    assert frase(vazia, AGORA, False) == "Simulação de hoje, 13:25, concluída: nada a lançar."


def test_frase_em_andamento():
    rodando = execucao(simulacao=True, resumo={"requisicoes": 5, "processadas": 1})
    assert frase(rodando, AGORA, False) == "Simulação em andamento: requisição 2 de 5."
    no_fim = execucao(resumo={"requisicoes": 5, "processadas": 5})
    assert frase(no_fim, AGORA, False) == "Lançamento em andamento: requisição 5 de 5."
    assert frase(execucao(resumo={}), AGORA, False) == (
        "Lançamento em andamento: preparando a fila."
    )


def test_frase_interrompida_e_falha():
    morta = execucao(simulacao=True, resumo={"requisicoes": 5, "processadas": 1})
    assert frase(morta, AGORA, True) == (
        "Simulação de hoje, 13:25, interrompida: o robô parou sem registrar o fim."
    )
    assert frase(falha(simulacao=False), AGORA, False) == "Lançamento de hoje, 13:25, falhou."


# --- Acompanhamento por requisição (resumo com `lotes`) ---


def lote(n, resultado="aguardando", inicio=None, fim=None, **campos):
    return {
        "lote": f"AV-{n:06d}",
        "recebedor": f"Pessoa {n}",
        "centro": "4",
        "itens": 1,
        "resultado": resultado,
        "requisicao": campos.pop("requisicao", ""),
        "mensagem": campos.pop("mensagem", ""),
        "inicio": inicio.isoformat() if inicio else "",
        "fim": fim.isoformat() if fim else "",
    }


def em(segundos):
    return AGORA + timedelta(seconds=segundos)


def test_etapa_do_log_em_portugues_pela_ultima_linha_reconhecida():
    log = (
        "13:20:00 → (1/2) AV-1 | ...\n13:20:01   reabrindo módulo Compras\n"
        "13:20:10 → (2/2) AV-2 | ...\n13:20:11   etapa: abrir formulário\n"
        "13:20:12   etapa: cabeçalho (data 14/10/2026)\n13:20:13     ok: combo\n"
        "13:20:14   etapa: itens\n13:20:15   item 3/17 (023.001.002): qtd 2\n"
        "13:20:16     ok: SABÃO | QTD 2\n"
    )
    assert etapa_do_log(log) == "Preenchendo o item 3 de 17"
    assert etapa_do_log(log + "13:20:20   🔎 conferência final (1/5): grade\n") == (
        "Conferindo o que foi digitado"
    )
    assert etapa_do_log(log + "13:20:21   etapa: salvar no SCPI\n") == "Salvando no SCPI"
    assert etapa_do_log("13:20:10 → (2/2) AV-2 | ...\n") == "Abrindo o formulário"
    assert etapa_do_log("13:20:10 → (2/2) AV-2 | ...\n13:20:11   reabrindo módulo Compras\n") == (
        "Preparando o SCPI para a próxima requisição"
    )
    assert etapa_do_log("") == "Trabalhando nesta requisição"


def test_etapa_do_log_nao_olha_a_requisicao_anterior():
    log = "13:20:00 → (1/2) AV-1\n13:20:01   etapa: salvar no SCPI\n13:20:10 → (2/2) AV-2\n"
    assert etapa_do_log(log) == "Abrindo o formulário"


def test_ultima_atividade_pela_hora_da_ultima_linha():
    assert ultima_atividade("13:24:56 algo\n", AGORA) == 4
    assert ultima_atividade("13:23:00 a\n\n", AGORA) == 120
    assert ultima_atividade("", AGORA) is None
    # Linha de antes da meia-noite lida logo depois dela.
    depois_da_meia_noite = timezone.make_aware(datetime(2026, 10, 15, 0, 0, 30))
    assert ultima_atividade("23:59:50 a\n", depois_da_meia_noite) == 40


def test_estimativa_pelo_tempo_medio_das_concluidas():
    lotes = [
        lote(1, "lancada", em(-200), em(-140)),
        lote(2, "lancada", em(-140), em(-80)),
        lote(3, "andamento", em(-20)),
        lote(4),
        lote(5),
    ]
    # média de 60 s: 40 s da atual + 2 × 60 s.
    assert estimativa(lotes, AGORA) == "faltam cerca de 3 min"
    assert estimativa([lote(1, "andamento", em(-5)), lote(2)], AGORA) is None
    assert estimativa(
        [lote(1, "lancada", em(-30), em(-20)), lote(2, "andamento", em(-1))], AGORA
    ) == ("falta menos de 1 min")


def execucao_com(lotes, fase="lancando", log="", **campos):
    resumo = {"requisicoes": campos.pop("requisicoes", len(lotes)), "fase": fase, "lotes": lotes}
    campos.setdefault("inicio", em(-300))
    return ExecucaoRobo(resumo=resumo, log=log, **campos)


def test_execucao_antiga_sem_lotes_nao_tem_acompanhamento():
    e = execucao(resumo={"requisicoes": 2, "processadas": 1})
    assert acompanhamento(e, AGORA, False) is None


def test_lancamento_em_andamento():
    e = execucao_com(
        [
            lote(
                1,
                "verificar",
                em(-200),
                em(-140),
                mensagem=(
                    "Resultado incerto: SCPI respondeu ao Salvar: "
                    "'Mês de Referência Diferente' ['Sim', 'Não']"
                ),
            ),
            lote(2, "lancada", em(-140), em(-80), requisicao="003712/26"),
            lote(3, "andamento", em(-20)),
            lote(4),
        ],
        log="13:24:50 → (3/4) AV-000003\n13:24:56   item 1/1 (008.001.002): qtd 2\n",
    )
    a = acompanhamento(e, AGORA, False)
    assert a.em_andamento and a.titulo == "Lançamento em andamento"
    assert a.tempo == "5 min decorridos"
    assert [(f.estado, f.texto) for f in a.fases] == [
        ("feita", "Feito"),
        ("atual", "2 de 4 feitas"),
        ("", ""),
    ]
    assert (a.feitas, a.total) == (2, 4)
    assert a.agora.linha.lote == "AV-000003" and a.agora.etapa == "Preenchendo o item 1 de 1"
    assert not a.agora.parado and a.agora.atividade == "Última atividade há 4 s"
    estados = [(linha.estado, linha.texto) for linha in a.linhas]
    assert estados == [
        ("aviso", "Conferir no SCPI"),
        ("ok", "Lançada"),
        ("atual", "Em andamento"),
        ("espera", "Aguardando"),
    ]
    assert a.linhas[1].requisicao == "003712/26"
    assert "não sabe se ela foi gravada" in a.linhas[0].detalhe
    assert "Mês de Referência Diferente" in a.linhas[0].detalhe
    assert a.contagem == "1 lançada · 1 para conferir · 1 aguardando"
    assert a.estimativa == "faltam cerca de 2 min"
    assert a.barra == {"ok": 25.0, "aviso": 25.0, "erro": 0.0, "fora": 0.0, "atual": 25.0}
    assert a.desfecho is None


def test_sem_novidade_ha_mais_de_um_minuto():
    e = execucao_com([lote(1, "andamento", em(-200)), lote(2)], log="13:23:20 → (1/2) AV-1\n")
    a = acompanhamento(e, AGORA, False)
    assert a.agora.parado and a.agora.rotulo == "Sem novidade há 1 min 40 s"
    assert "5 min" in a.agora.atividade


def test_lendo_o_scpi_antes_de_lancar():
    e = execucao_com([lote(1), lote(2)], fase="antes", requisicoes=0)
    a = acompanhamento(e, AGORA, False)
    assert [f.estado for f in a.fases] == ["atual", "", ""] and a.total == 2
    assert a.agora.linha is None and "Lendo no SCPI" in a.agora.etapa
    assert a.estimativa == "a estimativa aparece depois da primeira requisição"


def test_concluido_com_pendencias_aponta_as_travas():
    e = execucao_com(
        [
            lote(1, "verificar", em(-200), em(-140)),
            lote(2, "erro", em(-140), em(-80), mensagem="item 1/2: saldo insuficiente"),
            lote(3, "lancada", em(-80), em(-20), requisicao="003712/26"),
        ],
        fase="depois",
        situacao="ATENCAO",
        fim=AGORA,
    )
    a = acompanhamento(e, AGORA, False)
    assert not a.em_andamento and a.titulo == "Lançamento concluído com pendências"
    assert a.tempo == "levou 5 min" and a.agora is None and a.estimativa is None
    assert [f.estado for f in a.fases] == ["feita", "feita", "feita"]
    assert a.desfecho.tipo == "atencao" and a.desfecho.travas == 2
    assert "1 requisição precisa ser conferida no SCPI" in a.desfecho.titulo
    assert "1 requisição teve erro e não foi salva" in a.desfecho.texto
    assert a.linhas[1].texto == "Com erro, não foi salva"
    assert a.linhas[1].detalhe == "item 1/2: saldo insuficiente"


def test_simulacao_concluida_sem_fases_e_pronta_para_lancar():
    e = execucao_com(
        [lote(1, "simulada", em(-60), em(-30)), lote(2, "simulada", em(-30), em(-1))],
        simulacao=True,
        situacao="SUCESSO",
        fim=AGORA,
    )
    a = acompanhamento(e, AGORA, False)
    assert a.titulo == "Simulação concluída" and a.fases == []
    assert a.desfecho.tipo == "ok" and "prontas para lançar" in a.desfecho.texto
    assert {linha.texto for linha in a.linhas} == {"Preenchida e conferida"}
    assert a.contagem == "2 preenchidas"


def test_interrompida_marca_onde_parou():
    e = execucao_com(
        [lote(1, "lancada", em(-200), em(-140)), lote(2, "andamento", em(-140)), lote(3)],
    )
    a = acompanhamento(e, AGORA, True)
    assert not a.em_andamento and a.titulo == "Lançamento interrompido"
    assert a.agora is None and a.desfecho is None
    assert [linha.estado for linha in a.linhas] == ["ok", "erro", "fora"]
    assert a.linhas[1].texto == "O robô parou nesta requisição"
    assert a.linhas[2].texto == "Não chegou a ser processada"
    assert [f.estado for f in a.fases] == ["feita", "parou", ""]


def test_escolhidas_que_nao_foram_ao_scpi_ficam_fora_da_barra():
    e = execucao_com(
        [
            lote(1, "lancada", em(-60), em(-30)),
            lote(2, "ignorada", mensagem="Tem uma trava para conferir: não foi ao SCPI."),
        ],
        requisicoes=1,
        situacao="SUCESSO",
        fim=AGORA,
    )
    a = acompanhamento(e, AGORA, False)
    assert (a.feitas, a.total) == (1, 1)
    assert a.linhas[1].estado == "fora" and a.linhas[1].texto == "Deixada de fora"
    assert a.desfecho.tipo == "ok" and a.desfecho.titulo == "A requisição foi lançada no SCPI."


def test_ultima_atividade_ignora_o_rastro_de_uma_excecao():
    log = "13:24:50 ✘ Não foi possível\nTraceback (most recent call last):\n  File x\n"
    assert ultima_atividade(log, AGORA) == 10
    assert ultima_atividade("Traceback\n  File x\n", AGORA) is None


def test_sem_requisicao_para_o_scpi_nao_mostra_fases_nem_sucesso():
    e = execucao_com(
        [lote(1, "erro", mensagem="centro de custo 'X' não existe")],
        requisicoes=0,
        situacao="ATENCAO",
        fim=AGORA,
    )
    a = acompanhamento(e, AGORA, False)
    assert a.fases == [] and a.total == 0
    assert a.desfecho.tipo == "atencao" and a.desfecho.travas == 1


def test_nenhuma_lancada_nao_e_sucesso():
    e = execucao_com(
        [lote(1, "ignorada", em(-60), em(-30), mensagem="A requisição mudou.")],
        situacao="SUCESSO",
        fim=AGORA,
    )
    a = acompanhamento(e, AGORA, False)
    assert a.desfecho.tipo == "atencao" and a.desfecho.titulo == "Nenhuma requisição foi lançada."
    assert a.barra["fora"] == 100.0  # processada e deixada de fora: enche a barra


def test_simulacao_sem_nenhuma_preenchida_nao_e_sucesso():
    e = execucao_com(
        [lote(1, "ignorada", mensagem="Tem uma trava para conferir: não foi ao SCPI.")],
        requisicoes=0,
        simulacao=True,
        situacao="SUCESSO",
        fim=AGORA,
    )
    a = acompanhamento(e, AGORA, False)
    assert a.desfecho.titulo == "Nenhuma requisição foi preenchida."
