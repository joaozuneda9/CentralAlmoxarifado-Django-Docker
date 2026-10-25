"""A página Formulários (spec 009): o almoxarifado escolhe, por formulário, quais centros de custo
são destino e quais materiais são oferecidos.

Ver é de todo usuário do almoxarifado; gravar exige `is_staff` mais a permissão do cadastro
(`catalogo.acesso`), recusada no servidor. As gravações seguem o padrão POST, mensagem e
redirecionamento, voltando ao mesmo formulário, aba, filtro e página.
"""

from itertools import groupby
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from catalogo.acesso import exige, pode_alterar_centros, pode_alterar_materiais
from catalogo.catalogos import MODO_DESTINO, MODO_OFICINA, MODO_SEM_PLACA
from catalogo.disponibilidade import (
    ACOES,
    ACRESCENTADO,
    ACRESCENTAR,
    FORA,
    RESTAURAR,
    RETIRADO,
    RETIRAR,
    aplicar_em_lote,
    definir_ativo,
    definir_excecao,
    estados_do_material,
    habilitar_centros,
    materiais_da_tela,
    situacao_do_formulario,
)
from catalogo.forms import ESTADOS_DO_MATERIAL, FiltrosCentros, FiltrosMateriais
from catalogo.models import CentroCusto, CentroFormulario, Formulario, Material, ParDePara
from pedidos.regras import norm_placa, qtd_br, truncar_qtd

ABAS = [("centros", "Centros de custo"), ("materiais", "Materiais")]
POR_PAGINA = 50
PARAMETROS_DA_VOLTA = (
    "formulario",
    "aba",
    "qc",
    "centro_destino",
    "centro_estado",
    "centro_placa",
    "centro_uso",
    "q",
    "grupo",
    "subgrupo",
    "estado",
    "pagina",
)

# Como o formulário apresenta o destino, em palavras (a ajuda da aba Centros de custo).
EXPLICACAO_DO_MODO = {
    "padrao": (
        "O formulário oferece o centro pela descrição e, para a linha com placa, também como "
        "“descrição — placa”."
    ),
    MODO_SEM_PLACA: (
        "O formulário oferece só a descrição do centro, uma vez; a placa não importa. Por isso a "
        "escolha vale para todas as linhas da descrição."
    ),
    MODO_OFICINA: (
        "O formulário oferece a linha com placa só como “descrição — placa” e a linha sem placa "
        "pela descrição."
    ),
}

ORIGEM_EM_TEXTO = {
    ACRESCENTADO: "acrescentado pelo administrador",
    RETIRADO: "retirado pelo administrador",
    FORA: "fora da regra do formulário",
}


def _formulario(valor) -> str | None:
    return valor if valor in Formulario.values else None


def _url_da_pagina(parametros) -> str:
    """O endereço da página com o estado de quem gravou (formulário, aba, filtros, página)."""
    permitidos = {k: parametros.get(k) for k in PARAMETROS_DA_VOLTA if parametros.get(k)}
    consulta = urlencode(permitidos)
    return reverse("catalogo:formularios") + (f"?{consulta}" if consulta else "")


def _ids(valores) -> list[int]:
    ids = []
    for valor in valores:
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue
    return ids


# --- A página ----------------------------------------------------------------------------------


def _filtrar_centros(linhas, origem: str, filtros: dict, modo: str, habilitadas: set[int]):
    """Aplica a busca e os filtros da aba Centros de custo. O texto vale palavra por palavra (todas
    precisam aparecer) em descrição, código e placa; a placa também casa digitada com hífen ou
    espaço (`CZA-1614`). Nas viaturas (sem placa) o filtro de placa não existe."""
    for palavra in filtros.get("qc", "").split():
        condicao = Q(descricao__icontains=palavra) | Q(codigo__icontains=palavra)
        placa = norm_placa(palavra)
        if placa:
            condicao |= Q(placa__icontains=placa)
        linhas = linhas.filter(condicao)
    destino = filtros.get("centro_destino")
    if destino == "sim":
        linhas = linhas.filter(pk__in=habilitadas)
    elif destino == "nao":
        linhas = linhas.exclude(pk__in=habilitadas)
    estado = filtros.get("centro_estado")
    if estado:
        linhas = linhas.filter(ativo=(estado == "ativo"))
    placa = filtros.get("centro_placa")
    if placa and modo != MODO_SEM_PLACA:
        linhas = linhas.filter(placa__isnull=(placa == "sem"))
    uso = filtros.get("centro_uso")
    if uso == "sem_formulario":
        linhas = linhas.filter(ativo=True).exclude(
            pk__in=CentroFormulario.objects.values("centro_id")
        )
    elif uso == "outros":
        linhas = linhas.filter(
            pk__in=CentroFormulario.objects.exclude(formulario=origem).values("centro_id")
        )
    return linhas


def _contexto_centros(origem: str, filtros_centros: FiltrosCentros, usuario) -> dict:
    filtros = filtros_centros.filtros()
    habilitadas = set(
        CentroFormulario.objects.filter(formulario=origem).values_list("centro_id", flat=True)
    )
    modo = MODO_DESTINO[origem]
    linhas = _filtrar_centros(CentroCusto.objects.all(), origem, filtros, modo, habilitadas)
    # Em quais OUTROS formulários cada linha é destino (uma consulta só, na ordem dos formulários).
    outros: dict[int, list[str]] = {}
    ordem = {valor: i for i, valor in enumerate(Formulario.values)}
    pares = CentroFormulario.objects.exclude(formulario=origem).values_list(
        "centro_id", "formulario"
    )
    for centro_id, formulario in sorted(pares, key=lambda par: ordem[par[1]]):
        outros.setdefault(centro_id, []).append(Formulario(formulario).label)
    grupos = []
    for descricao, conjunto in groupby(linhas, key=lambda c: c.descricao):
        itens = [
            {"centro": c, "habilitada": c.pk in habilitadas, "outros": outros.get(c.pk, [])}
            for c in conjunto
        ]
        grupos.append(
            {
                "descricao": descricao,
                "linhas": itens,
                "outros": list(dict.fromkeys(f for i in itens for f in i["outros"])),
                "ids": [i["centro"].pk for i in itens],
                "n_habilitadas": sum(1 for i in itens if i["habilitada"]),
                "n_inativas": sum(1 for i in itens if not i["centro"].ativo),
                "codigos": list(dict.fromkeys(i["centro"].codigo for i in itens)),
            }
        )
    return {
        "grupos": grupos,
        "modo": modo,
        "explicacao_do_modo": EXPLICACAO_DO_MODO[modo],
        "por_descricao": modo == MODO_SEM_PLACA,
        "total_linhas": sum(len(g["linhas"]) for g in grupos),
        "total_habilitadas": sum(g["n_habilitadas"] for g in grupos),
        "filtros_centros": filtros_centros,
        "filtros_centros_ativos": filtros,
        "volta_centros": {nome: filtros.get(nome, "") for nome in FiltrosCentros.base_fields},
        "pode_alterar_centros": pode_alterar_centros(usuario),
        "pode_criar_centro": usuario.is_staff and usuario.has_perm("catalogo.add_centrocusto"),
        "pode_editar_centro": usuario.is_staff and usuario.has_perm("catalogo.change_centrocusto"),
        "sem_centros": not CentroCusto.objects.exists(),
    }


def _texto_do_estado(estado) -> dict:
    """O que a tela diz de um estado: o selo (nível e texto) e a origem em palavras."""
    if estado.oculto:
        selo = ("aviso", "Oculto no cadastro")
    elif estado.disponivel:
        selo = ("ok", "Disponível")
    else:
        selo = ("neutro", "Não disponível")
    origem = (
        "pela regra do formulário" if estado.origem == "regra" else ORIGEM_EM_TEXTO[estado.origem]
    )
    if estado.oculto:
        origem = "o cadastro do SCPI o oculta em todos os formulários"
    return {"nivel": selo[0], "selo": selo[1], "origem": origem}


def _contexto_materiais(request, origem: str, pode_alterar: bool) -> dict:
    formulario_de_filtros = FiltrosMateriais(request.GET)
    filtros = formulario_de_filtros.filtros()
    situacao = situacao_do_formulario(origem)
    consulta = materiais_da_tela(origem, filtros, situacao)
    pagina = Paginator(consulta, POR_PAGINA).get_page(request.GET.get("pagina"))
    materiais = list(pagina.object_list)
    antigos = dict(
        ParDePara.objects.filter(antigo__in=[m.codigo for m in materiais]).values_list(
            "antigo", "novo"
        )
    )
    linhas = []
    for m in materiais:
        estado = situacao.estado(m)
        linhas.append(
            {
                "material": m,
                "estado": estado,
                "texto": _texto_do_estado(estado),
                "tem_excecao": m.codigo in situacao.excecoes,
                "saldo": qtd_br(truncar_qtd(m.estoque)),
                "canonico": antigos.get(m.codigo, ""),
            }
        )
    return {
        "linhas": linhas,
        "pagina": pagina,
        "filtros_materiais": formulario_de_filtros,
        "filtros_ativos": filtros,
        "lote_query": urlencode({"formulario": origem, **filtros}),
        "total_materiais": pagina.paginator.count,
        "pode_alterar_materiais": pode_alterar,
    }


@login_required
def formularios(request):
    origem = _formulario(request.GET.get("formulario")) or Formulario.LIMPEZA
    aba = request.GET.get("aba")
    aba = aba if aba in {chave for chave, _ in ABAS} else "materiais"
    usuario = request.user
    contexto = {
        "formulario": origem,
        "formulario_nome": Formulario(origem).label,
        "lista_de_formularios": [(f.value, f.label) for f in Formulario],
        "aba": aba,
        "abas": ABAS,
        **_contexto_centros(origem, FiltrosCentros(request.GET), usuario),
        **_contexto_materiais(request, origem, pode_alterar_materiais(usuario)),
        "pode_alterar_algo": pode_alterar_centros(usuario) or pode_alterar_materiais(usuario),
    }
    return render(request, "catalogo/formularios.html", contexto)


# --- Gravações ---------------------------------------------------------------------------------


@login_required
@require_POST
@exige(pode_alterar_centros)
def formularios_centros(request):
    origem = _formulario(request.POST.get("formulario"))
    if origem is None:
        return HttpResponseBadRequest("Formulário desconhecido.")
    ids = _ids(request.POST.getlist("centro"))
    habilitar = request.POST.get("habilitado") == "1"
    alvo = Formulario(origem).label
    if not ids:
        messages.warning(request, "Nenhum centro de custo foi escolhido.")
    else:
        mudaram = habilitar_centros(origem, ids, habilitar, request.user)
        if not mudaram:
            messages.info(request, "Nada mudou: os centros já estavam assim.")
        else:
            if habilitar:
                feito = "habilitada" if mudaram == 1 else "habilitadas"
            else:
                feito = "desabilitada" if mudaram == 1 else "desabilitadas"
            linhas = "linha" if mudaram == 1 else "linhas"
            messages.success(request, f"{mudaram} {linhas} {feito} em {alvo}.")
    return redirect(_url_da_pagina({**request.POST.dict(), "aba": "centros"}))


@login_required
@require_POST
@exige(pode_alterar_centros)
def formularios_ativo(request):
    """Ativa ou inativa linhas de centro, globalmente: o inativo não é oferecido em formulário
    nenhum, mas a escolha de cada formulário fica guardada."""
    origem = _formulario(request.POST.get("formulario")) or Formulario.LIMPEZA
    ids = _ids(request.POST.getlist("centro"))
    ativar = request.POST.get("ativo") == "1"
    if not ids:
        messages.warning(request, "Nenhum centro de custo foi escolhido.")
    else:
        mudaram = definir_ativo(ids, ativar)
        if not mudaram:
            messages.info(request, "Nada mudou: os centros já estavam assim.")
        else:
            feito = ("ativada" if ativar else "inativada") + ("" if mudaram == 1 else "s")
            linhas = "linha" if mudaram == 1 else "linhas"
            messages.success(request, f"{mudaram} {linhas} {feito}.")
    return redirect(_url_da_pagina({**request.POST.dict(), "formulario": origem, "aba": "centros"}))


@login_required
@require_POST
@exige(pode_alterar_materiais)
def formularios_excecao(request):
    origem = _formulario(request.POST.get("formulario"))
    acao = request.POST.get("acao")
    if origem is None or acao not in ACOES:
        return HttpResponseBadRequest("Pedido inválido.")
    material = get_object_or_404(Material, codigo=request.POST.get("codigo", ""))
    mudou = definir_excecao(origem, material, acao, request.user)
    alvo = Formulario(origem).label
    nome = f"{material.codigo} — {material.nome}"
    if not mudou:
        messages.info(request, f"Nada mudou para {nome}: já estava assim em {alvo}.")
    elif acao == ACRESCENTAR:
        messages.success(request, f"{nome} passou a ser oferecido em {alvo}.")
    elif acao == RETIRAR:
        messages.success(request, f"{nome} deixou de ser oferecido em {alvo}.")
    elif acao == RESTAURAR:
        messages.success(request, f"{nome} voltou à regra de {alvo}.")
    return redirect(_url_da_pagina({**request.POST.dict(), "aba": "materiais"}))


# --- Lote: prévia e confirmação, em duas telas (também sem JavaScript) -----------------------


def _resumo_do_lote(mudaram: int, ja_estavam: int) -> str:
    mudou = "mudou" if mudaram == 1 else "mudaram"
    estava = "já estava assim" if ja_estavam == 1 else "já estavam assim"
    return f"{mudaram} {mudou} e {ja_estavam} {estava}"


def _filtros_em_texto(filtros: dict) -> list[tuple[str, str]]:
    """Os filtros do lote como a tela os diz: (rótulo, valor legível)."""
    estados = dict(ESTADOS_DO_MATERIAL)
    rotulos = [
        ("q", "Busca"),
        ("grupo", "Grupo"),
        ("subgrupo", "Subgrupo"),
        ("estado", "No formulário"),
    ]
    return [
        (
            rotulo,
            estados.get(filtros[chave], filtros[chave]) if chave == "estado" else filtros[chave],
        )
        for chave, rotulo in rotulos
        if chave in filtros
    ]


@login_required
def formularios_lote(request):
    """GET é a prévia (formulário, ação, número exato e uma amostra); POST confirma e aplica a
    **todos** os materiais do filtro, numa só transação. Recusa, sem mudar nada, se o número do
    filtro mudou desde a prévia ou se faltou o "ciente" do catálogo inteiro (sem filtro)."""
    dados = request.POST if request.method == "POST" else request.GET
    origem = _formulario(dados.get("formulario"))
    acao = dados.get("acao")
    if origem is None or acao not in (ACRESCENTAR, RETIRAR):
        return HttpResponseBadRequest("Pedido inválido.")
    filtros_do_lote = FiltrosMateriais(dados)
    if not filtros_do_lote.is_valid():
        # Na lista da página um filtro desconhecido some; no lote ele alargaria o alcance da
        # alteração sem ninguém ver: aqui é erro.
        return HttpResponseBadRequest("Filtro inválido.")
    filtros = filtros_do_lote.filtros()
    consulta = materiais_da_tela(origem, filtros, situacao_do_formulario(origem))
    total = consulta.count()
    parametros = {"formulario": origem, "acao": acao, **filtros}
    if request.method == "POST":
        if not pode_alterar_materiais(request.user):
            raise PermissionDenied("Sem permissão para alterar a configuração dos formulários.")
        previa = reverse("catalogo:formularios_lote") + "?" + urlencode(parametros)
        if dados.get("total") != str(total):
            messages.warning(
                request,
                f"O número de materiais do filtro mudou (a prévia mostrava {dados.get('total')} e "
                f"agora são {total}). Confira de novo antes de confirmar.",
            )
            return redirect(previa)
        if not filtros and not dados.get("ciente"):
            messages.warning(
                request,
                "Sem filtro, a operação alcança o catálogo inteiro: marque que está ciente para "
                "confirmar.",
            )
            return redirect(previa)
        mudaram, ja_estavam = aplicar_em_lote(origem, consulta, acao, request.user)
        messages.success(
            request, f"{_resumo_do_lote(mudaram, ja_estavam)} em {Formulario(origem).label}."
        )
        return redirect(_url_da_pagina({"formulario": origem, "aba": "materiais", **filtros}))
    contexto = {
        "formulario": origem,
        "formulario_nome": Formulario(origem).label,
        "acao": acao,
        "acao_texto": "Acrescentar ao formulário"
        if acao == ACRESCENTAR
        else "Retirar do formulário",
        "total": total,
        "amostra": list(consulta[:10]),
        "filtros_ativos": filtros,
        "filtros_em_texto": _filtros_em_texto(filtros),
        "sem_filtro": not filtros,
        "pode_alterar_materiais": pode_alterar_materiais(request.user),
        "voltar": _url_da_pagina({"formulario": origem, "aba": "materiais", **filtros}),
    }
    return render(request, "catalogo/formularios_lote.html", contexto)


# --- Onde um material aparece ------------------------------------------------------------------


@login_required
def formularios_material(request, codigo):
    """Os cinco formulários com o estado e a origem do material (histórias de consulta); aberta a
    todo usuário do almoxarifado. Mostra também o oculto, que a lista da página não traz."""
    material = get_object_or_404(Material, codigo=codigo)
    canonico = (
        ParDePara.objects.filter(antigo=material.codigo).values_list("novo", flat=True).first()
    )
    linhas = []
    for origem, estado in estados_do_material(material):
        linhas.append(
            {
                "origem": origem,
                "nome": Formulario(origem).label,
                "estado": estado,
                "texto": _texto_do_estado(estado),
                "url": _url_da_pagina(
                    {"formulario": origem, "aba": "materiais", "q": material.codigo}
                ),
            }
        )
    contexto = {
        "material": material,
        "linhas": linhas,
        "canonico": canonico or "",
        "saldo": qtd_br(truncar_qtd(material.estoque)),
    }
    return render(request, "catalogo/formularios_material.html", contexto)
