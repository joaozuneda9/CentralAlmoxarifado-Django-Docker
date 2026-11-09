"""Quem abre cada parte do sistema.

Dois mecanismos, um para cada público:

- **Papéis da área interna (spec 012)**: o código pergunta por permissões próprias (`ATENDER`,
  `AUTOMACOES`, `CURVA`, `FORMULARIOS`), e os grupos `Atendimento` e `Gestão` as reúnem no admin.
  `REGRAS_POR_ROTA` diz o que cada rota nomeada exige; o `contas.middleware.ExigirPermissao` a
  aplica e nega por padrão a rota fora dela, o menu (`interface.navegacao`) só mostra o que a rota
  abre e um teste confere que toda rota está aqui. O superusuário passa em todas as permissões.
- **Segurança do Trabalho (spec 008)**: o usuário do grupo `GRUPO_SEGURANCA_TRABALHO` só abre as
  rotas de `ROTAS_SEGURANCA_TRABALHO` (`contas.middleware.RestringirSegurancaTrabalho`). O acesso é
  a participação no grupo, nunca `is_staff` nem permissão: o superusuário passa em qualquer
  `has_perm`, e quem decide um pedido de EPI precisa ser da Segurança do Trabalho.

Toda recusa vira uma linha do logger `contas.acesso` (`registrar_recusa`).
"""

import logging
from dataclasses import dataclass
from urllib.parse import quote

logger = logging.getLogger("contas.acesso")

GRUPO_SEGURANCA_TRABALHO = "Segurança do Trabalho"

# As únicas rotas (nome com namespace) abertas ao usuário do grupo: a entrada e a saída, a fila e a
# decisão dos pedidos de EPI e as páginas públicas, que qualquer pessoa abre. Tudo o mais é negado
# por padrão, inclusive rota que alguém crie depois.
ROTAS_SEGURANCA_TRABALHO = frozenset(
    {
        "login",
        "logout",
        "pedidos:autorizacoes",
        "pedidos:autorizacao",
        "pedidos:decidir",
        "pedidos:inicio",
        "pedidos:formulario",
        "pedidos:materiais",
        "pedidos:carrinho",
        "pedidos:consulta_epi",
        "pedidos:consulta",
    }
)

# Permissões da área interna (declaradas no `Meta` de `contas.Usuario`).
ATENDER = "contas.atender_pedidos"
AUTOMACOES = "contas.operar_automacoes"
CURVA = "contas.ver_curva"
FORMULARIOS = "contas.ver_formularios"
PERMISSOES_INTERNAS = (ATENDER, AUTOMACOES, CURVA, FORMULARIOS)

GRUPO_ATENDIMENTO = "Atendimento"
GRUPO_GESTAO = "Gestão"


@dataclass(frozen=True)
class Regra:
    """O que uma rota interna exige, com o texto que a recusa mostra."""

    permissoes: tuple[str, ...]
    motivo: str
    exige_staff: bool = False

    def falta(self, usuario) -> str:
        """O que falta ao usuário, para o log (permissões e `is_staff`)."""
        faltam = [p for p in self.permissoes if not usuario.has_perm(p)]
        if self.exige_staff and not usuario.is_staff:
            faltam.append("is_staff")
        return ",".join(faltam) or "-"


# Categorias que não são uma `Regra`: quem decide é outra camada.
PUBLICA = "publica"  # qualquer pessoa
ADMIN = "admin"  # o admin do Django (is_staff e permissões nativas)
SEGURANCA = "seguranca"  # as views da spec 008 (participação no grupo)

_ATENDIMENTO = Regra((ATENDER,), "Esta página é de quem atende os pedidos.")
_AUTOMACOES = Regra((AUTOMACOES,), "Esta página é de quem opera as automações.")
_CURVA = Regra((CURVA,), "Esta página é da gestão do almoxarifado.")
_FORMULARIOS = Regra((FORMULARIOS,), "Esta página é da gestão do almoxarifado.")
_ALTERAR = "Alterar os formulários exige acesso aos cadastros e a permissão do cadastro afetado."
_ALTERAR_CENTROS = Regra((FORMULARIOS, "catalogo.change_centrocusto"), _ALTERAR, True)
_ALTERAR_MATERIAIS = Regra((FORMULARIOS, "catalogo.change_excecaomaterial"), _ALTERAR, True)

# A fonte única de quem abre cada rota nomeada (contrato em
# specs/012-papeis-de-acesso/contracts/tabela-de-rotas.md). Rota nova entra aqui no mesmo PR.
REGRAS_POR_ROTA: dict[str, Regra | str] = {
    "login": PUBLICA,
    "logout": PUBLICA,
    "pedidos:inicio": PUBLICA,
    "pedidos:formulario": PUBLICA,
    "pedidos:materiais": PUBLICA,
    "pedidos:carrinho": PUBLICA,
    "pedidos:consulta": PUBLICA,
    "pedidos:consulta_epi": PUBLICA,
    "pedidos:autorizacoes": SEGURANCA,
    "pedidos:autorizacao": SEGURANCA,
    "pedidos:decidir": SEGURANCA,
    "pedidos:painel": _ATENDIMENTO,
    "pedidos:detalhe": _ATENDIMENTO,
    "pedidos:atender": _ATENDIMENTO,
    "pedidos:editar": _ATENDIMENTO,
    "pedidos:atendimento_materiais": _ATENDIMENTO,
    "pedidos:atendimento_adicionar": _ATENDIMENTO,
    "pedidos:avulsa": _ATENDIMENTO,
    "pedidos:avulsa_materiais": _ATENDIMENTO,
    "pedidos:avulsa_carrinho": _ATENDIMENTO,
    "pedidos:marcar_impressos": _ATENDIMENTO,
    "automacoes:pagina": _AUTOMACOES,
    "automacoes:atualizar": _AUTOMACOES,
    "automacoes:importar": _AUTOMACOES,
    "automacoes:lancar": _AUTOMACOES,
    "automacoes:resolver": _AUTOMACOES,
    "automacoes:conferir": _AUTOMACOES,
    "automacoes:corrigir": _AUTOMACOES,
    "catalogo:curva": _CURVA,
    "catalogo:formularios": _FORMULARIOS,
    "catalogo:formularios_material": _FORMULARIOS,
    # A prévia do lote é leitura (GET); a aplicação (POST) passa ainda pelo `exige` da view.
    "catalogo:formularios_lote": _FORMULARIOS,
    "catalogo:formularios_centros": _ALTERAR_CENTROS,
    "catalogo:formularios_ativo": _ALTERAR_CENTROS,
    "catalogo:formularios_excecao": _ALTERAR_MATERIAIS,
    "catalogo:formularios_regra": _ALTERAR_MATERIAIS,
}


def regra_da_rota(view_name: str | None) -> Regra | str | None:
    """A regra ou a categoria da rota (o namespace `admin` é `ADMIN`); None fora da tabela."""
    if not view_name:
        return None
    if view_name.startswith("admin:"):
        return ADMIN
    return REGRAS_POR_ROTA.get(view_name)


def pode(usuario, regra: Regra) -> bool:
    """Se o usuário cumpre a regra: autenticado, ativo, `is_staff` se pedido e as permissões."""
    if usuario is None or not usuario.is_authenticated or not usuario.is_active:
        return False
    if regra.exige_staff and not usuario.is_staff:
        return False
    return usuario.has_perms(regra.permissoes)


def pode_abrir(usuario, view_name: str) -> bool:
    """Se o usuário abre a rota, pela tabela (o menu e os links usam isto)."""
    regra = regra_da_rota(view_name)
    if regra == PUBLICA:
        return True
    if usuario is None or not usuario.is_authenticated:
        return False
    if regra == ADMIN:
        return usuario.is_staff
    if regra == SEGURANCA:
        return da_seguranca_trabalho(usuario)
    if isinstance(regra, Regra):
        return pode(usuario, regra)
    return usuario.is_superuser


def sem_papel(usuario) -> bool:
    """Autenticado, sem nenhuma permissão da área interna e fora da Segurança do Trabalho."""
    if usuario is None or not usuario.is_authenticated:
        return False
    if da_seguranca_trabalho(usuario):
        return False
    return not any(usuario.has_perm(p) for p in PERMISSOES_INTERNAS)


def _campo_do_log(texto: str) -> str:
    """O texto com espaços, quebras de linha, `%` e caracteres invisíveis em `%XX` (o `unquote`
    devolve o original): um valor vindo do cadastro não cria campo nem linha falsa no log."""
    return "".join(
        quote(c, safe="") if c.isspace() or c == "%" or not c.isprintable() else c for c in texto
    )


def registrar_recusa(request, falta: str) -> None:
    """Uma linha no log por recusa de acesso: quem, qual rota, qual método e o que faltou.

    Nunca o caminho com parâmetros, a query string, o corpo, cookies ou cabeçalhos: o número do
    pedido e os nomes de solicitantes não vão ao log.
    """
    correspondencia = getattr(request, "resolver_match", None)
    registrar_recusa_de(
        request.user,
        correspondencia.view_name if correspondencia else "-",
        request.method,
        falta,
    )


def registrar_recusa_de(usuario, rota: str, metodo: str, falta: str) -> None:
    """A linha da recusa, também fora de uma requisição (o disparo do lançamento): o formato e a
    codificação da matrícula ficam num lugar só."""
    logger.warning(
        "Acesso recusado: matricula=%s rota=%s metodo=%s falta=%s",
        _campo_do_log(usuario.get_username()) if usuario.is_authenticated else "-",
        rota,
        metodo,
        falta,
    )


def da_seguranca_trabalho(usuario) -> bool:
    """Se o usuário está autenticado e é do grupo da Segurança do Trabalho.

    O resultado fica guardado no próprio objeto: o middleware, o menu e a view consultam o mesmo
    `request.user` no pedido, e a consulta ao banco sai uma vez só. Quem muda os grupos e
    pergunta de novo precisa de um objeto novo (`refresh_from_db` não apaga o guardado).
    """
    if usuario is None or not usuario.is_authenticated:
        return False
    if not hasattr(usuario, "_da_seguranca_trabalho"):
        usuario._da_seguranca_trabalho = usuario.groups.filter(
            name=GRUPO_SEGURANCA_TRABALHO
        ).exists()
    return usuario._da_seguranca_trabalho
