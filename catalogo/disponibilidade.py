"""Disponibilidade dos materiais e dos centros de custo nos formulários (spec 009).

A disponibilidade efetiva de um material num formulário é a regra de origem de hoje mais as exceções
do administrador, sempre respeitando o cadastro (material oculto nunca é oferecido):

    efetiva = (regra_de_origem − retirados) ∪ acrescentados

`estado` é a regra pura (sem ORM, Princípio I); os serviços que gravam ficam no fim do módulo.
"""

from dataclasses import dataclass

# De onde vem a disponibilidade (ou a falta dela) de um material num formulário.
REGRA = "regra"  # a regra de origem o traz e nenhuma exceção o retira
ACRESCENTADO = "acrescentado"  # a regra não o traz; uma exceção o acrescenta
RETIRADO = "retirado"  # a regra o traz; uma exceção o retira
FORA = "fora"  # a regra não o traz e nada o acrescenta


@dataclass(frozen=True)
class Estado:
    disponivel: bool
    origem: str
    # A exceção não muda nada: retirar o que a regra não traz, ou acrescentar o que ela já traz.
    sem_efeito: bool
    # Oculto no cadastro: vale em todos os formulários e vence qualquer exceção.
    oculto: bool = False


def estado(oculto: bool, na_regra: bool, excecao: bool | None) -> Estado:
    """O estado efetivo do material no formulário. `excecao` é `True` (acrescenta), `False`
    (retira) ou `None` (sem exceção). Material oculto nunca está disponível, mas a origem e o "sem
    efeito" são os que valeriam sem o oculto, para a tela explicar."""
    if na_regra:
        if excecao is False:
            disponivel, origem, sem_efeito = False, RETIRADO, False
        else:
            disponivel, origem, sem_efeito = True, REGRA, excecao is True
    elif excecao is True:
        disponivel, origem, sem_efeito = True, ACRESCENTADO, False
    else:
        disponivel, origem, sem_efeito = False, FORA, excecao is False
    return Estado(disponivel and not oculto, origem, sem_efeito, oculto)


# ---------------------------------------------------------------------------
# Situação de um formulário e serviços que gravam (spec 009)
# ---------------------------------------------------------------------------

ACRESCENTAR = "acrescentar"
RETIRAR = "retirar"
RESTAURAR = "restaurar"
ACOES = (ACRESCENTAR, RETIRAR, RESTAURAR)
TAMANHO_DO_BLOCO = 1000  # materiais por consulta (IN) nas operações em lote


def excecao_para(na_regra: bool, disponivel_desejado: bool) -> bool | None:
    """A exceção mínima que leva o material ao resultado pedido: nenhuma se a regra de origem já
    dá esse resultado; senão, `True` (acrescentar) ou `False` (retirar). Pura."""
    return None if disponivel_desejado == na_regra else disponivel_desejado


@dataclass(frozen=True)
class SituacaoDoFormulario:
    """O que a regra de origem traz e as exceções gravadas, por código de material."""

    na_regra: frozenset[str]
    excecoes: dict[str, bool]

    def estado(self, material) -> Estado:
        return estado(
            material.oculto, material.codigo in self.na_regra, self.excecoes.get(material.codigo)
        )

    @property
    def efetivos(self) -> set[str]:
        """Os códigos disponíveis (sem filtrar os ocultos, que a consulta de materiais já tira)."""
        retirados = {c for c, habilitado in self.excecoes.items() if not habilitado}
        acrescentados = {c for c, habilitado in self.excecoes.items() if habilitado}
        return (set(self.na_regra) - retirados) | acrescentados


def situacao_do_formulario(origem: str, ab=None) -> SituacaoDoFormulario:
    """Calculada na hora: a regra de origem do formulário e as exceções dele. `ab` reaproveita o
    catálogo AB que o chamador já calculou (a conta pesada)."""
    from catalogo.catalogos import regra_de_origem
    from catalogo.models import ExcecaoMaterial

    excecoes = dict(
        ExcecaoMaterial.objects.filter(formulario=origem).values_list(
            "material__codigo", "habilitado"
        )
    )
    return SituacaoDoFormulario(
        na_regra=frozenset(i.codigo for i in regra_de_origem(origem, ab)), excecoes=excecoes
    )


def _gravar_excecao(origem, material, alvo: bool | None, usuario) -> bool:
    """Grava a exceção `alvo` (None: apaga). Devolve se algo mudou."""
    from django.utils import timezone

    from catalogo.models import ExcecaoMaterial

    atual = ExcecaoMaterial.objects.filter(formulario=origem, material=material).first()
    if alvo is None:
        if atual is None:
            return False
        atual.delete()
        return True
    if atual is not None and atual.habilitado == alvo:
        return False
    # INSERT ... ON DUPLICATE KEY UPDATE: dois administradores gravando o mesmo material ao
    # mesmo tempo deixam uma linha só e nenhum erro, e a última vale (o `update_or_create` falha
    # na corrida).
    ExcecaoMaterial.objects.bulk_create(
        [
            ExcecaoMaterial(
                formulario=origem,
                material=material,
                habilitado=alvo,
                alterado_por=usuario,
                alterado_em=timezone.now(),
            )
        ],
        update_conflicts=True,
        update_fields=["habilitado", "alterado_por", "alterado_em"],
    )
    return True


def restaurar_regra(origem: str) -> tuple[int, int]:
    """Restaura a regra padrão de um formulário: apaga todas as exceções de material dele, e o
    formulário volta a oferecer exatamente o que a regra de origem dá. Devolve (acrescentados que
    saíram, retirados que voltaram). Não toca o material, o estoque nem nenhum pedido; os outros
    formulários não mudam. Idempotente."""
    from django.db import transaction

    from catalogo.models import ExcecaoMaterial

    with transaction.atomic():
        excecoes = ExcecaoMaterial.objects.filter(formulario=origem)
        acrescentados = excecoes.filter(habilitado=True).count()
        retirados = excecoes.filter(habilitado=False).count()
        excecoes.delete()
    return acrescentados, retirados


def definir_excecao(origem: str, material, acao: str, usuario=None) -> bool:
    """Acrescenta, retira ou restaura (apaga a exceção) um material num formulário, com a menor
    mudança: se a regra de origem já dá o resultado pedido, a exceção é apagada. Idempotente.
    Devolve se algo mudou. Não toca o material, o estoque nem nenhum pedido."""
    from django.db import transaction

    if acao not in ACOES:
        raise ValueError(f"Ação desconhecida: {acao!r}")
    with transaction.atomic():
        if acao == RESTAURAR:
            return _gravar_excecao(origem, material, None, usuario)
        na_regra = material.codigo in situacao_do_formulario(origem).na_regra
        alvo = excecao_para(na_regra, acao == ACRESCENTAR)
        return _gravar_excecao(origem, material, alvo, usuario)


def aplicar_em_lote(origem: str, materiais, acao: str, usuario=None) -> tuple[int, int]:
    """Acrescenta ou retira de um formulário todos os `materiais` (um queryset), numa só
    transação: ou vale tudo, ou nada. Cada material recebe a menor mudança (apaga a exceção
    quando a regra já dá o resultado). Devolve `(mudaram, ja_estavam)`: os que já estavam como
    pedido (disponíveis ou não, pela regra mais a exceção) não mudam."""
    from django.db import transaction
    from django.utils import timezone

    from catalogo.models import ExcecaoMaterial

    if acao not in (ACRESCENTAR, RETIRAR):
        raise ValueError(f"Ação desconhecida: {acao!r}")
    desejado = acao == ACRESCENTAR
    mudaram = ja_estavam = 0
    with transaction.atomic():
        na_regra = situacao_do_formulario(origem).na_regra
        pares = list(materiais.values_list("pk", "codigo"))
        agora = timezone.now()
        for inicio in range(0, len(pares), TAMANHO_DO_BLOCO):
            bloco = pares[inicio : inicio + TAMANHO_DO_BLOCO]
            ids = [pk for pk, _ in bloco]
            atuais = dict(
                ExcecaoMaterial.objects.filter(formulario=origem, material_id__in=ids).values_list(
                    "material_id", "habilitado"
                )
            )
            gravar, apagar = [], []
            for pk, codigo in bloco:
                regra = codigo in na_regra
                atual = atuais.get(pk)
                if (regra if atual is None else atual) == desejado:
                    ja_estavam += 1
                    continue
                mudaram += 1
                alvo = excecao_para(regra, desejado)
                if alvo is None:
                    apagar.append(pk)
                else:
                    gravar.append(
                        ExcecaoMaterial(
                            material_id=pk,
                            formulario=origem,
                            habilitado=alvo,
                            alterado_por=usuario,
                            alterado_em=agora,
                        )
                    )
            if apagar:
                ExcecaoMaterial.objects.filter(formulario=origem, material_id__in=apagar).delete()
            if gravar:
                ExcecaoMaterial.objects.bulk_create(
                    gravar,
                    # MySQL e MariaDB: o conflito é o da constraint única, sem `unique_fields`.
                    update_conflicts=True,
                    update_fields=["habilitado", "alterado_por", "alterado_em"],
                )
    return mudaram, ja_estavam


def habilitar_centros(origem: str, centros, habilitado: bool, usuario=None) -> int:
    """Habilita ou desabilita linhas de centro (objetos ou ids) como destino de um formulário.
    Idempotente; devolve quantas associações mudaram. Habilitar cria só as que faltam; desabilitar
    apaga as existentes. Id que não existe é ignorado."""
    from django.db import transaction

    from catalogo.models import CentroCusto, CentroFormulario

    ids = {getattr(c, "pk", c) for c in centros}
    with transaction.atomic():
        if not habilitado:
            return CentroFormulario.objects.filter(formulario=origem, centro_id__in=ids).delete()[0]
        existentes = set(
            CentroFormulario.objects.filter(formulario=origem, centro_id__in=ids).values_list(
                "centro_id", flat=True
            )
        )
        faltam = set(
            CentroCusto.objects.filter(pk__in=ids - existentes).values_list("pk", flat=True)
        )
        CentroFormulario.objects.bulk_create(
            [
                CentroFormulario(centro_id=pk, formulario=origem, alterado_por=usuario)
                for pk in faltam
            ],
            ignore_conflicts=True,
        )
        return len(faltam)


def definir_ativo(centros, ativo: bool) -> int:
    """Ativa ou inativa linhas de centro (objetos ou ids), globalmente; as associações com os
    formulários ficam guardadas. Idempotente; devolve quantas linhas mudaram."""
    from catalogo.models import CentroCusto

    ids = {getattr(c, "pk", c) for c in centros}
    return CentroCusto.objects.filter(pk__in=ids).exclude(ativo=ativo).update(ativo=ativo)


def materiais_da_tela(origem: str, filtros: dict, situacao: SituacaoDoFormulario):
    """Os materiais **visíveis** do catálogo que a página lista, filtrados no banco e ordenados
    por nome e código. `filtros` vem de `FiltrosMateriais.filtros()`. O estado no formulário
    restringe pelos conjuntos de códigos da `situacao` (uma só conta por requisição); o catálogo
    inteiro nunca é carregado."""
    from django.db.models import Q

    from catalogo.models import Material

    consulta = Material.objects.filter(oculto=False)
    for palavra in (filtros.get("q") or "").split():
        consulta = consulta.filter(Q(nome__icontains=palavra) | Q(codigo__icontains=palavra))
    if grupo := filtros.get("grupo"):
        consulta = consulta.filter(grupo=grupo)
    if subgrupo := filtros.get("subgrupo"):
        consulta = consulta.filter(subgrupo=subgrupo)
    estado_pedido = filtros.get("estado")
    if estado_pedido == "disponivel":
        consulta = consulta.filter(codigo__in=situacao.efetivos)
    elif estado_pedido == "indisponivel":
        consulta = consulta.exclude(codigo__in=situacao.efetivos)
    elif estado_pedido == "excecao":
        consulta = consulta.filter(codigo__in=list(situacao.excecoes))
    return consulta.order_by("nome", "codigo")


def estados_do_material(material) -> list[tuple[str, Estado]]:
    """O estado do material em cada um dos cinco formulários, na ordem de `Formulario` (a
    consulta "onde este material aparece e por quê"). Calcula a regra de origem de cada um, com o
    catálogo AB (a conta pesada, base do AB e das viaturas) calculado uma vez só."""
    from catalogo.catalogos import catalogo_ab
    from catalogo.models import Formulario

    ab = catalogo_ab()
    return [
        (origem, situacao_do_formulario(origem, ab).estado(material))
        for origem in Formulario.values
    ]
