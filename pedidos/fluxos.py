"""Os formulários que montam um carrinho de materiais: limpeza, AB e viaturas (públicos) e saída
avulsa.

Cada formulário é uma entrada de `FLUXOS`, com só o que muda: o catálogo, os textos, a origem, a
regra de quantidade e, se precisar, a folha, os destinos aceitos e o número da ocorrência. Busca,
carrinho, envio, proteções e recibo são o núcleo, igual para todos, e não perguntam pelo nome nem
pela origem do formulário. Um formulário novo é uma entrada aqui, uma função de catálogo e um valor
novo em `Pedido.Origem` (com a migration de `choices`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from django.conf import settings
from django.http import Http404

from catalogo.catalogos import (
    ItemCatalogo,
    centros_do_formulario,
    folha_viaturas,
    formulario_ab,
    formulario_avulsa,
    formulario_epis,
    formulario_limpeza,
    formulario_oficina,
    formulario_viaturas,
)
from pedidos.regras import (
    AB,
    AVULSA,
    EPIS,
    LIMPEZA,
    OFICINA,
    REGRA_LIVRE,
    REGRA_POR_UNIDADE,
    VIATURAS,
    Centro,
    maximo_pedivel,
    normalizar_busca,
    qtd_br,
)

LIMITE_RESULTADOS = 50


@dataclass(frozen=True)
class Fluxo:
    nome: str  # usado na URL
    origem: str  # o valor gravado em `Pedido.origem`
    titulo: str  # nos formulários públicos, o nome que o funcionário vê (o interno é o da Origem)
    # O catálogo do formulário: None quando ele está indisponível (saldo nunca importado ou
    # nenhum item), nunca uma lista vazia.
    catalogo: Callable[[], list[ItemCatalogo] | None]
    exemplo_busca: str  # o exemplo no campo de busca
    exemplo_inicio: str = ""  # o exemplo no cartão da página inicial
    icone: str = "caixa"  # o ícone do cartão da página inicial
    exemplo_destino: str = "Setor, posto ou placa"  # no campo de destino
    rotulo_destino: str = "Destino dos materiais"  # o rótulo do campo de destino
    publico: bool = True
    # Quem pede segue a unidade do material (`por_unidade`); a equipe aceita fração em qualquer
    # unidade (`livre`).
    regra_quantidade: str = REGRA_POR_UNIDADE
    # Os códigos da folha (a lista preenchida de uma vez, num diálogo), na ordem; None: sem folha.
    folha: Callable[[], list[str]] | None = None
    # Os centros de custo aceitos como destino; None: todos os cadastrados (a saída avulsa). Os
    # formulários públicos leem a configuração (`centros_do_formulario`, spec 009).
    centros: Callable[[], list[Centro]] | None = None
    # Mostra, grava e compara no reenvio o "Nº da ocorrência" (opcional para quem pede).
    pede_ocorrencia: bool = False
    # O pedido passa por autorização da Segurança do Trabalho antes do atendimento (spec 008): o
    # registro cria a `AutorizacaoPedido` e o aviso ao almoxarifado só sai depois de autorizado.
    exige_autorizacao: bool = False
    # O formulário para o que não se encaixa nos outros: na página inicial, um cartão à parte,
    # depois dos outros, com `titulo_inicio` (quando preenchido) no lugar do título.
    geral: bool = False
    titulo_inicio: str = ""

    @property
    def max_itens(self) -> int | None:
        return settings.PEDIDOS_MAX_ITENS if self.publico else None

    # Textos do carrinho: o funcionário monta um pedido; o almoxarifado, os materiais de uma saída.
    @property
    def rotulo_carrinho(self) -> str:
        return "Seu pedido" if self.publico else "Materiais da saída"

    @property
    def rotulo_revisar(self) -> str:
        return "Revisar e enviar" if self.publico else "Revisar e registrar"

    @property
    def rotulo_enviar(self) -> str:
        return "Enviar pedido" if self.publico else "Registrar saída"

    @property
    def icone_enviar(self) -> str:
        return "enviar" if self.publico else "saida"


FLUXOS: dict[str, Fluxo] = {
    "limpeza": Fluxo(
        nome="limpeza",
        origem=LIMPEZA,
        titulo="Limpeza, copa e escritório",
        catalogo=formulario_limpeza,
        exemplo_busca="Ex.: detergente, café",
        exemplo_inicio="Ex.: café, copo descartável, água sanitária, caneta",
        icone="caixa",
        exemplo_destino="Setor ou posto de trabalho",
        centros=partial(centros_do_formulario, LIMPEZA),
    ),
    "viaturas": Fluxo(
        nome="viaturas",
        origem=VIATURAS,
        titulo="Reposição de peças das viaturas",
        catalogo=formulario_viaturas,
        exemplo_busca="Ex.: luva, tubo, registro",
        exemplo_inicio="Ex.: cotovelo, luva, tee, registro, tubo",
        icone="atualizar",
        exemplo_destino="Centro de custo da equipe",
        rotulo_destino="Número da viatura",
        folha=folha_viaturas,
        centros=partial(centros_do_formulario, VIATURAS),
        pede_ocorrencia=True,
    ),
    "ab": Fluxo(
        nome="ab",
        origem=AB,
        titulo="Ferramentas, peças e materiais",
        catalogo=formulario_ab,
        exemplo_busca="Ex.: luva, fita veda rosca",
        exemplo_inicio="Ex.: ferramenta, cimento, fita veda-rosca",
        icone="catalogo",
        centros=partial(centros_do_formulario, AB),
        geral=True,
        titulo_inicio="Ferramentas, peças e outros materiais",
    ),
    "oficina": Fluxo(
        nome="oficina",
        origem=OFICINA,
        titulo="Oficina mecânica",
        catalogo=formulario_oficina,
        exemplo_busca="Ex.: filtro de óleo, pneu",
        exemplo_inicio="Ex.: filtro, óleo, pneu, aditivo, lâmpada",
        icone="chave-inglesa",
        exemplo_destino="Oficina mecânica ou placa da viatura",
        centros=partial(centros_do_formulario, OFICINA),
    ),
    "epis": Fluxo(
        nome="epis",
        origem=EPIS,
        titulo="Equipamentos de proteção individual (EPIs)",
        catalogo=formulario_epis,
        exemplo_busca="Ex.: luva, capacete, óculos",
        exemplo_inicio="Ex.: luva, botina, capacete, protetor auricular",
        icone="escudo",
        exemplo_destino="Setor ou posto de trabalho",
        centros=partial(centros_do_formulario, EPIS),
        exige_autorizacao=True,
    ),
    "avulsa": Fluxo(
        nome="avulsa",
        origem=AVULSA,
        titulo="Saída avulsa",
        catalogo=formulario_avulsa,
        exemplo_busca="Ex.: luva, fita veda rosca, 016.005.010",
        publico=False,
        regra_quantidade=REGRA_LIVRE,
    ),
}


def fluxo_publico(nome: str) -> Fluxo:
    fluxo = FLUXOS.get(nome)
    if fluxo is None or not fluxo.publico:
        raise Http404("Formulário desconhecido.")
    return fluxo


def fluxos_publicos() -> list[Fluxo]:
    """Os formulários que o funcionário vê na página inicial, na ordem de `FLUXOS`."""
    return [f for f in FLUXOS.values() if f.publico]


def fluxo_da_origem(origem: str) -> Fluxo | None:
    return next((f for f in FLUXOS.values() if f.origem == origem), None)


def _ordenados(valores) -> list[str]:
    return sorted({v for v in valores if v}, key=normalizar_busca)


def opcoes_filtro(fluxo: Fluxo, catalogo) -> list:
    """Formulários públicos: [(grupo, [subgrupos])] dos materiais do catálogo. Avulsa: nenhum
    filtro."""
    catalogo = catalogo or []
    if fluxo.publico:
        return [
            (grupo, _ordenados(i.subgrupo for i in catalogo if i.grupo == grupo))
            for grupo in _ordenados(i.grupo for i in catalogo)
        ]
    return []


def classe_ab(item: ItemCatalogo) -> str:
    return " › ".join(p for p in (item.grupo, item.subgrupo) if p)


def _passa(fluxo: Fluxo, item: ItemCatalogo, filtro: str) -> bool:
    if not filtro:
        return True
    if fluxo.publico:
        return filtro in (item.grupo, classe_ab(item))
    return True


def _texto_busca(fluxo: Fluxo, item: ItemCatalogo) -> str:
    return item.nome if fluxo.publico else f"{item.nome} {item.codigo}"


def buscar(fluxo: Fluxo, catalogo, q: str, filtro: str) -> tuple[list[ItemCatalogo], int]:
    """Itens cujo nome contém todas as palavras de `q` (sem acento): os que podem ser pedidos
    primeiro e os bloqueados (sem estoque, duplicados) no fim, cada grupo na ordem do catálogo
    (nas viaturas, por nome); os primeiros `LIMITE_RESULTADOS` e o total. A ordenação vem antes
    do corte, para nenhum material que pode ser pedido ficar de fora. Só a saída avulsa (equipe)
    busca também pelo código; os formulários públicos procuram só pelo nome."""
    from pedidos.carrinho import motivo_bloqueio

    palavras = normalizar_busca(q).split()
    achados = [
        i
        for i in catalogo or []
        if _passa(fluxo, i, filtro)
        and all(p in normalizar_busca(_texto_busca(fluxo, i)) for p in palavras)
    ]
    if fluxo.folha is not None:
        # A ordem da lista de peças (a folha em papel) vale só para a folha; na busca, é por nome.
        achados.sort(key=lambda i: (normalizar_busca(i.nome), i.codigo))
    achados.sort(key=lambda i: bool(motivo_bloqueio(fluxo, i)))  # estável: mantém a ordem
    return achados[:LIMITE_RESULTADOS], len(achados)


@dataclass(frozen=True)
class Resultado:
    """Um material na lista de resultados, já com o que a tela mostra."""

    item: ItemCatalogo
    motivo: str  # por que não pode ser pedido ("" se pode)
    info: str  # a unidade ("—" sem unidade)
    classe: str
    # "Estoque N": o máximo que o formulário aceita (o mesmo número do limite e das mensagens),
    # sem zeros à direita.
    estoque: str = ""

    @property
    def linha_publica(self) -> str:
        """A informação do formulário público (sem código nem grupo): estoque e unidade."""
        unidade = "" if self.info == "—" else self.info
        return " · ".join(p for p in (self.estoque, unidade) if p) or self.info


def resultados(fluxo: Fluxo, itens) -> list[Resultado]:
    from pedidos.carrinho import motivo_bloqueio

    lista = []
    for i in itens:
        maximo = maximo_pedivel(i.estoque, i.fracionavel, fluxo.regra_quantidade)
        estoque = f"Estoque {qtd_br(maximo)}"
        classe = classe_ab(i) if fluxo.publico else i.grupo
        lista.append(Resultado(i, motivo_bloqueio(fluxo, i), i.unidade or "—", classe, estoque))
    return lista
