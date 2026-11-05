"""Download dos relatórios do SCPI pelo Playwright.

Não é coberto pelos testes automáticos: só se exercita contra o SCPI real (os comandos aceitam
`--arquivo` para pular esta parte). A navegação vem do `run()` de `exportar_produtos_cadastro.py`,
`exportar_estoque.py` e `exportar_saidas.py` do extrair-relatorio (commit
cce15aa3706be09bf1cdb2b6c8768b2ab9a4a622), com duas mudanças para vários relatórios caberem numa
sessão só (`sessao_compartilhada`, usada pelo `atualizar_catalogo`):

- os campos do Relatório de Produtos são achados pelo que está na tela (a legenda do quadro, o
  rótulo acima do campo), nunca pelo ID: o SCPI numera os IDs na ordem em que as telas são
  criadas na sessão, e a segunda abertura do mesmo relatório já tem outros;
- cada relatório termina como começou: "Fechar relatório" fecha o visualizador e "Sair" fecha o
  formulário, que na próxima abertura volta com os valores padrão.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from django.conf import settings

from scpi.browser import abrir_sessao, frame_compras, interceptar_csv, orm_liberado
from scpi.leitura import ErroImportacao, NadaAExibir

# Início do período de cadastro pedido ao SCPI: antes de qualquer material (os mais antigos
# têm DTAINSERE 01/01/2014), para o relatório trazer o cadastro inteiro.
INICIO_CADASTRO = date(2000, 1, 1)

# Quanto esperar o SCPI gerar cada relatório depois de "Imprimir", até o link "Salvar Arquivo"
# aparecer. O cadastro inteiro (a primeira carga, de 2000 até hoje) pode levar muitos minutos; no
# original eram 60s, o que estourava o tempo antes de o relatório ficar pronto. O download do CSV
# tem a sua própria espera (`scpi.browser.interceptar_csv`).
ESPERA_GERACAO_CADASTRO_MS = 20 * 60 * 1000
ESPERA_GERACAO_ESTOQUE_MS = 5 * 60 * 1000
ESPERA_GERACAO_SAIDAS_MS = 5 * 60 * 1000

# Tipos de produto pedidos ao SCPI no cadastro, um relatório para cada: ficam de fora Serviços e
# Combustíveis. As linhas dos relatórios são juntadas antes da gravação (`leitura.ler_cadastro`).
TIPOS_CADASTRO = ("Produtos", "Peças", "Lubrificantes", "Pneus")

TITULO_PRODUTOS = "Relatório de Produtos / Servi"

# IDs ExtJS dinâmicos — acha inputs por posição Y no form
JS_IDS_SAIDAS = """
    (() => {
        const byY = (sel, minY, maxY) =>
            [...document.querySelectorAll(sel)]
            .map(el => ({id: el.id, r: el.getBoundingClientRect()}))
            .filter(e => e.r.y >= minY && e.r.y <= maxY && e.r.width > 10)
            .sort((a, b) => a.r.x - b.r.x || a.r.y - b.r.y)
            .map(e => e.id);
        return {
            datas: byY('input[data-ref="inputEl"][type="text"]', 80, 130),
            combos: [...document.querySelectorAll('[id$="-trigger-picker"]')]
                .map(t => ({id: t.id, y: t.getBoundingClientRect().y}))
                .filter(t => t.y > 130 && t.y < 400)
                .sort((a, b) => a.y - b.y)
                .map(t => t.id)
        };
    })()
"""

# ID (o desta abertura) do campo logo abaixo de um rótulo, na janela visível com o título dado:
# o campo visível cujo topo fica até 40px abaixo do rótulo e que cruza a sua coluna.
JS_CAMPO_ABAIXO_DO_ROTULO = """([titulo, rotulo]) => {
    const visivel = e => e.offsetParent !== null;
    const janela = [...document.querySelectorAll('.x-window')]
        .find(w => visivel(w) && w.textContent.includes(titulo));
    if (!janela) return null;
    const texto = [...janela.querySelectorAll('*')]
        .find(e => visivel(e) && e.children.length === 0 && e.textContent.trim() === rotulo);
    if (!texto) return null;
    const r = texto.getBoundingClientRect();
    const campo = [...janela.querySelectorAll('input[type="text"]')]
        .filter(visivel)
        .map(i => ({i, c: i.getBoundingClientRect()}))
        .filter(({c}) => c.top >= r.bottom - 2 && c.top - r.bottom <= 40)
        .filter(({c}) => c.left <= r.right && c.right >= r.left)
        .sort((a, b) => a.c.top - b.c.top)[0];
    return campo ? campo.i.id : null;
}"""


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


class _Sessao:
    """Navegador logado no SCPI, já no módulo COMPRAS."""

    def __init__(self, perfil: str):
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        try:
            self.context, self.page = abrir_sessao(
                self._playwright, settings.SCPI_PERFIL_DIR / perfil
            )
            try:
                self.frame = frame_compras(self.page)
            except BaseException:
                self.context.close()
                raise
        except BaseException:
            self._playwright.stop()
            raise

    def fechar(self) -> None:
        try:
            self.context.close()
        finally:
            self._playwright.stop()


# A sessão aberta por `sessao_compartilhada`, que os relatórios usam em vez de abrir a sua.
_compartilhada: dict = {}


@contextmanager
def sessao_compartilhada() -> Iterator[None]:
    """Os relatórios baixados dentro do bloco usam um navegador só, aberto no primeiro que precisar
    dele (nenhum, se todos vierem de arquivo) e fechado no fim. Um relatório que falha fecha a
    sessão: o SCPI pode ter ficado numa tela qualquer, e o seguinte abre outra, do zero."""
    _compartilhada.clear()
    _compartilhada["ativa"] = True
    with orm_liberado():
        try:
            yield
        finally:
            sessao = _compartilhada.pop("sessao", None)
            _compartilhada.clear()
            if sessao:
                sessao.fechar()


@contextmanager
def _sessao(perfil: str) -> Iterator[_Sessao]:
    """A sessão compartilhada, se houver; senão, uma só para este relatório."""
    if not _compartilhada.get("ativa"):
        sessao = _Sessao(perfil)
        try:
            yield sessao
        finally:
            sessao.fechar()
        return
    if "sessao" not in _compartilhada:
        _compartilhada["sessao"] = _Sessao("catalogo")
    try:
        yield _compartilhada["sessao"]
    except BaseException:
        _compartilhada.pop("sessao").fechar()
        raise


def _abrir_relatorio_produtos(frame):
    """Cadastros › Produtos › Imprimir › Relatório de Produtos / Serviços. Devolve o diálogo."""
    produtos = frame.locator("div").filter(has_text=re.compile(r"^Produtos$"), visible=True)
    # "Cadastros" abre e fecha o ramo do menu: só é clicado se o ramo ainda está fechado
    if not produtos.count():
        frame.locator("div").filter(has_text=re.compile(r"^Cadastros$")).click()
    produtos.click()

    frame.locator("a").filter(has_text="Imprimir", visible=True).click()
    frame.get_by_role("menuitem", name=TITULO_PRODUTOS).click()

    dialog = frame.get_by_label(TITULO_PRODUTOS)
    dialog.get_by_role("button", name="Imprimir").wait_for(state="visible")
    return dialog


def _campo_abaixo(frame, rotulo: str):
    id_ = frame.evaluate(JS_CAMPO_ABAIXO_DO_ROTULO, ["Relatório de Produtos", rotulo])
    if not id_:
        raise ErroImportacao(f"SCPI: campo '{rotulo}' não encontrado no Relatório de Produtos.")
    return frame.locator(f"#{id_}")


def _escolher(frame, campo, opcao: str) -> None:
    # trigger-picker do combo é instável ao clique sintético do Playwright;
    # abre a lista via foco + seta (comportamento nativo do ExtJS)
    campo.click()
    campo.press("ArrowDown")
    item = frame.get_by_role("option", name=opcao, exact=True).filter(visible=True)
    item.wait_for(state="visible")
    item.click()


def _gerar(frame, timeout: int) -> bool:
    """Depois de "Imprimir": espera o relatório e diz se ele saiu. Sem nada no filtro, o SCPI não
    gera o relatório e só avisa "Nada a exibir!!!"; o OK do aviso devolve ao formulário."""
    # Só os visíveis: o visualizador do relatório anterior pode continuar no DOM, escondido.
    salvar = frame.locator("a").filter(has_text="Salvar Arquivo", visible=True)
    nada = frame.get_by_text("Nada a exibir").filter(visible=True)
    salvar.or_(nada).first.wait_for(timeout=timeout)
    if not nada.count():
        return True
    # o aviso é a última janela aberta: o seu OK é o último botão OK visível
    frame.locator("a.x-btn").filter(has_text=re.compile(r"^\s*OK\s*$"), visible=True).last.click()
    nada.first.wait_for(state="detached")
    return False


def _fechar_relatorio(frame) -> None:
    """Fecha o visualizador; o formulário do relatório volta à frente."""
    frame.locator("a.x-btn").filter(has_text="Fechar relatório", visible=True).click()
    frame.locator("a.x-btn").filter(has_text="Fechar relatório", visible=True).first.wait_for(
        state="detached"
    )


def baixar_cadastro(de: date, ate: date) -> list[bytes]:
    """Um Relatório de Produtos / Serviços por tipo de `TIPOS_CADASTRO`, pelo período de cadastro.

    Depois de cada CSV, "Fechar relatório" volta ao formulário, que guarda o período e as opções:
    só o tipo muda de um relatório para o outro. Tipo sem material no período fica sem CSV."""
    with _sessao("cadastro") as sessao:
        frame = sessao.frame
        dialog = _abrir_relatorio_produtos(frame)

        periodo = dialog.locator("fieldset").filter(has_text="Período do Cadastro")
        de_input, ate_input = periodo.locator('input[type="text"]').all()[:2]
        de_input.fill(_br(de))
        de_input.press("Tab")
        ate_input.fill(_br(ate))
        ate_input.press("Tab")

        partes = []
        for tipo in TIPOS_CADASTRO:
            _escolher(frame, _campo_abaixo(frame, "Tipos de Produtos"), tipo)
            dialog.get_by_role("button", name="Imprimir").click()
            if not _gerar(frame, timeout=ESPERA_GERACAO_CADASTRO_MS):
                continue
            partes.append(interceptar_csv(sessao.page, frame, f"cadastro-{tipo.lower()}"))
            _fechar_relatorio(frame)

        dialog.get_by_role("button", name="Sair").click()
        dialog.wait_for(state="hidden")
        return partes


def baixar_estoque() -> bytes:
    """Relatório de Produtos / Serviços com Situação = "Apenas com Estoque"."""
    with _sessao("estoque") as sessao:
        frame = sessao.frame
        dialog = _abrir_relatorio_produtos(frame)

        _escolher(frame, _campo_abaixo(frame, "Situação"), "Apenas com Estoque")
        dialog.get_by_role("button", name="Imprimir").click()
        if not _gerar(frame, timeout=ESPERA_GERACAO_ESTOQUE_MS):
            raise ErroImportacao("Estoque: o SCPI não tem nenhum material com estoque.")
        conteudo = interceptar_csv(sessao.page, frame, "estoque")
        _fechar_relatorio(frame)

        dialog.get_by_role("button", name="Sair").click()
        dialog.wait_for(state="hidden")
        return conteudo


def baixar_saidas(de: date, ate: date) -> bytes:
    """Relação de Requisições de saída (BALCÃO) no período."""
    return _relacao_de_requisicoes(de, ate, tipo="BALCÃO", rotulo="Saídas do SCPI", perfil="saidas")


def baixar_requisicoes(de: date, ate: date) -> bytes:
    """Relação de Requisições de saída de **todos os tipos** no período (spec 010): o registro
    oficial da conciliação. O período filtra pela coluna DTPAG."""
    return _relacao_de_requisicoes(
        de, ate, tipo=None, rotulo="Requisições do SCPI", perfil="requisicoes"
    )


def _relacao_de_requisicoes(
    de: date, ate: date, *, tipo: str | None, rotulo: str, perfil: str
) -> bytes:
    """Relatórios › Requisições › Relação de Requisições, "Requisições de Saída", no período;
    com `tipo`, só as requisições daquele tipo (o primeiro combo); sem ele, todas."""
    with _sessao(perfil) as sessao:
        frame = sessao.frame

        frame.get_by_role("button", name="Relatórios").click()
        frame.get_by_role("menuitem", name="Requisições").hover()
        frame.get_by_role("menuitem", name="Relação de Requisições").click()

        frame.get_by_role("radio", name="Requisições de Saída").check()

        ids = frame.evaluate(JS_IDS_SAIDAS)

        # preenche datas (De/Até) — primeiro e segundo input na banda y≈100
        frame.locator(f"#{ids['datas'][0]}").fill(_br(de))
        frame.locator(f"#{ids['datas'][0]}").press("Tab")
        frame.locator(f"#{ids['datas'][1]}").fill(_br(ate))
        frame.locator(f"#{ids['datas'][1]}").press("Tab")

        if tipo is not None:
            # combos ordenados por Y: [0]=tipo da requisição
            # inputEl = trigger ID com sufixo trocado
            def abrir_combo(trigger_id: str) -> None:
                input_id = trigger_id.replace("-trigger-picker", "-inputEl")
                frame.locator(f"#{input_id}").hover()
                frame.locator(f"#{trigger_id}").click()

            abrir_combo(ids["combos"][0])
            frame.get_by_role("option", name=tipo).click()

        frame.get_by_role("button", name="Imprimir").click()
        if not _gerar(frame, timeout=ESPERA_GERACAO_SAIDAS_MS):
            if tipo is None:
                # Sem filtro de tipo, "Nada a exibir" é um período sem nenhuma requisição: a
                # extração decide se isso vale (conciliacao.extracao._vazio).
                raise NadaAExibir(f"{rotulo}: nada a exibir de {_br(de)} a {_br(ate)}.")
            raise ErroImportacao(
                f"{rotulo}: nenhuma requisição de saída de {_br(de)} a {_br(ate)}."
            )
        conteudo = interceptar_csv(sessao.page, frame, perfil)
        if not conteudo:
            raise ErroImportacao(f"{rotulo}: o SCPI entregou um CSV vazio.")
        _fechar_relatorio(frame)
        return conteudo
