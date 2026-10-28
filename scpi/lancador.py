"""Navegação do lançamento de saídas no SCPI (Playwright) e a classe que a expõe ao robô.

Não é coberto pelos testes automáticos: só se exercita contra o SCPI real (os testes usam um
SCPI simulado, atrás do protocolo `scpi.lancamento.SCPI`). A navegação vem sem mudança do
`lancar_saidas.py` do extrair-relatorio (commit cce15aa3706be09bf1cdb2b6c8768b2ab9a4a622):
seletores, esperas, JS e a ordem dos campos são os do original. Mudam só a origem dos dados
(`Requisicao` no lugar das linhas da planilha), o `log` (logger `scpi.lancamento`), o perfil do
navegador (`settings.SCPI_PERFIL_DIR / "lancamento"`) e o `processar`, que vira os métodos de
`NavegadorSCPI`.

Caminho no SCPI: COMPRAS → Movimento → Requisição de Saída → Inserir → Produto ▾ →
Lançamento Manual. Depois de salvar, o SCPI abre "Controle de Manutenção Preventiva"
(itens com veículo) e "Imprimir Requisições", e por fim esvazia o iframe do Compras — o robô
fecha tudo e reabre o módulo (Fechar → COMPRAS) antes da próxima requisição.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from pedidos.regras import norm_placa
from pedidos.regras import norm_u as norm
from scpi.browser import abrir_sessao, frame_compras, orm_liberado
from scpi.requisicoes import RE_CADPRO, RE_REQUI, ErroSCPI, Item, Requisicao, ResultadoIncerto

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page

TIMEOUT = 60000
PAUSA_ENTRE_ACOES_MS = 100  # entre as ações do preenchimento dos itens da saída

log = logging.getLogger("scpi.lancamento").info


def resumo_erro(e: BaseException) -> str:
    """Primeira linha do erro + o seletor que o Playwright estava esperando, se houver."""
    linhas = [linha.strip() for linha in str(e).splitlines() if linha.strip()]
    alvo = next((linha for linha in linhas if linha.startswith("- waiting for")), "")
    return f"{type(e).__name__}: {linhas[0] if linhas else ''}" + (f" [{alvo[2:]}]" if alvo else "")


def parse_decimal_br(valor: str) -> Decimal:
    """Número no formato pt-BR: '1.234,5' → 1234.5 ; '0,33' → 0.33 ; '9.999' → 9999."""
    return Decimal(valor.strip().replace(".", "").replace(",", "."))


# ---------------------------------------------------------------- SCPI

# rótulos do formulário são <label class="x-component"> soltos, acima do input;
# IDs ExtJS são dinâmicos — acha o input pela posição logo abaixo do rótulo
JS_INPUT_POR_ROTULO = """
(rotulo) => {
    const vis = e => e.offsetParent !== null;
    const lab = [...document.querySelectorAll('label.x-component')]
        .find(l => vis(l) && l.textContent.trim().replace(/:$/, '') === rotulo);
    if (!lab) return null;
    const lr = lab.getBoundingClientRect();
    const alvo = [...document.querySelectorAll('input[data-ref="inputEl"], textarea[data-ref="inputEl"]')]
        .filter(vis)
        .map(i => ({id: i.id, r: i.getBoundingClientRect()}))
        .filter(e => e.r.width > 10 && e.r.top >= lr.bottom - 2 && e.r.top - lr.bottom < 30
                     && Math.abs(e.r.left - lr.left) < 15)
        .sort((a, b) => a.r.top - b.r.top)[0];
    return alvo ? alvo.id : null;
}
"""  # noqa: E501

# caixas de mensagem visíveis e com texto (o SCPI mantém uma .x-message-box vazia no DOM)
JS_MENSAGEM_VISIVEL = """
() => {
    const box = [...document.querySelectorAll('.x-message-box')]
        .find(el => el.offsetParent !== null && el.innerText.trim());
    if (!box) return null;
    const botoes = [...box.querySelectorAll('.x-btn')].filter(b => b.offsetParent !== null)
        .map(b => b.innerText.trim()).filter(Boolean);
    const titulo = box.querySelector('.x-window-header')?.innerText.trim() || '';
    const corpo = box.querySelector('.x-window-body')?.innerText.trim() || box.innerText.trim();
    return {titulo, texto: corpo, botoes};
}
"""

# títulos das janelas (não message-box) abertas
JS_JANELAS = """
() => [...document.querySelectorAll('.x-window:not(.x-message-box)')]
    .filter(w => w.offsetParent !== null)
    .map(w => w.querySelector('.x-window-header')?.innerText.trim() || '')
    .filter(Boolean)
"""

# grid de itens: lê todas as linhas como {cabeçalho: texto}
JS_LER_ITENS = """
() => {
    const vis = e => e.offsetParent !== null;
    const grid = [...document.querySelectorAll('.x-grid')].filter(vis)
        .find(g => g.innerText.includes('Descrição do Produto/Serviço'));
    if (!grid) return null;
    const cols = [...grid.querySelectorAll('.x-column-header')]
        .map(h => [h.innerText.trim(), h.id]).filter(([t]) => t);
    return [...grid.querySelectorAll('.x-grid-item')].map(r => Object.fromEntries(
        cols.map(([t, id]) => [t, r.querySelector(`[data-columnid="${id}"]`)?.innerText.trim() ?? ''])
    ));
}
"""  # noqa: E501

# Recarrega a grade do servidor (o mesmo pedido que o "Novo Item" faz) e espera a resposta.
JS_RECARREGAR_GRADE = """
() => new Promise(resolve => {
    const E = window.Ext;
    const grade = E && E.ComponentQuery.query('grid').find(g => g.isVisible()
        && g.getColumns().some(c => (c.text || '').includes('Descrição do Produto/Serviço')));
    if (!grade) return resolve(false);
    const fim = setTimeout(() => resolve(false), 8000);
    // o evento `load` também dispara quando a carga falha: vale o `successful` do callback
    grade.store.load({callback: (registros, operacao, sucesso) => {
        clearTimeout(fim);
        resolve(Boolean(sucesso));
    }});
})
"""

# O "Novo Item" faz o SCPI recarregar a grade inteira do servidor (JSON com `rows`, colunas
# "1" = código, "6" = QTD, "8" = total). Só diagnóstico: guarda o que cada recarga devolveu, sem
# alterar nada.
JS_DIAGNOSTICO_INSTALAR = """
() => {
    if (window.__diagGrade) return true;
    if (!window.Ext || !window.Ext.Ajax) return false;
    window.__diagGrade = [];
    window.Ext.Ajax.on('requestcomplete', (conn, resp) => {
        try {
            const txt = resp.responseText || '';
            if (!txt.startsWith('{"metaData"')) return;
            const j = JSON.parse(txt);
            window.__diagGrade.push((j.rows || []).map(r => [r['1'], r['6'], r['8']]));
        } catch (e) {}
    });
    return true;
}
"""

JS_DIAGNOSTICO_LER = """
() => window.__diagGrade ? window.__diagGrade.splice(0) : []
"""

# nº gerado aparece logo abaixo do rótulo "Requisição" (canto superior esquerdo do formulário)
JS_NUMERO_REQUISICAO = """
() => {
    const lab = [...document.querySelectorAll('label.x-component')]
        .find(l => l.offsetParent !== null && l.textContent.trim() === 'Requisição');
    if (!lab) return '';
    const lr = lab.getBoundingClientRect();
    return [...document.querySelectorAll('label, div, span, input')]
        .filter(e => e.offsetParent !== null && e !== lab)
        .filter(e => { const r = e.getBoundingClientRect();
            return r.top >= lr.top - 5 && r.top < lr.bottom + 30 && r.left >= lr.left - 5 && r.left < lr.right + 80; })
        .map(e => e.value || (e.children.length === 0 ? e.textContent : ''))
        .join(' ');
}
"""  # noqa: E501


def aguardar_mascara(frame: Frame) -> None:
    # só o "carregando" (.x-mask-msg); máscaras de janelas modais ficam visíveis e vazias
    frame.wait_for_function(
        "!Array.from(document.querySelectorAll('.x-mask-msg')).some(el => el.offsetParent !== null)",  # noqa: E501
        timeout=TIMEOUT,
    )
    frame.page.wait_for_timeout(300)


def campo(frame: Frame, rotulo: str):
    """Input ExtJS pelo texto do rótulo (IDs são dinâmicos)."""
    input_id = frame.evaluate(JS_INPUT_POR_ROTULO, rotulo)
    if not input_id:
        raise ErroSCPI(f"campo '{rotulo}' não encontrado no formulário")
    return frame.locator(f"#{input_id}")


def mensagem_scpi(frame: Frame) -> dict | None:
    return frame.evaluate(JS_MENSAGEM_VISIVEL)


def responder_mensagem(frame: Frame, botao: str) -> None:
    caixa = frame.locator(".x-message-box").filter(has_text=re.compile(r"\S"))
    caixa.get_by_role("button", name=botao, exact=True).first.click()
    aguardar_mascara(frame)


def janela(frame: Frame, titulo: str):
    return (
        frame.locator(".x-window:not(.x-message-box)")
        .filter(has=frame.locator(".x-window-header", has_text=titulo))
        .first
    )


def checar_mensagem(frame: Frame, etapa: str) -> None:
    """Responde perguntas conhecidas; qualquer outra caixa de mensagem aborta a etapa."""
    for _ in range(5):
        msg = mensagem_scpi(frame)
        if not msg:
            return
        texto = " ".join(msg["texto"].split())
        # centro de custo de veículo: óleo/peças não são combustível
        if "Saída de Combustível" in texto and "Não" in msg["botoes"]:
            log(f"  SCPI perguntou '{texto}' → Não")
            responder_mensagem(frame, "Não")
            continue
        if "OK" in msg["botoes"]:
            responder_mensagem(frame, "OK")
        raise ErroSCPI(f"{etapa}: SCPI respondeu '{texto}'")


def sair_do_campo(frame: Frame, entrada, etapa: str) -> None:
    """Tab dispara o lookup de código/descrição do ExtJS; checa a resposta."""
    entrada.press("Tab")
    aguardar_mascara(frame)
    checar_mensagem(frame, etapa)


def selecionar_combo(frame: Frame, rotulo: str, opcao: str) -> None:
    # trigger-picker é instável ao clique sintético; abre via foco + seta
    entrada = campo(frame, rotulo)
    entrada.click()
    entrada.press("ArrowDown")
    item = frame.locator(".x-boundlist-item").filter(has_text=re.compile(rf"^{re.escape(opcao)}$"))
    item.first.wait_for(state="visible", timeout=TIMEOUT)
    item.first.click()
    if norm(entrada.input_value()) != norm(opcao):
        raise ErroSCPI(f"combo '{rotulo}' ficou com '{entrada.input_value()}', esperado '{opcao}'")


def abrir_tela_saida(frame: Frame) -> None:
    """Abre a aba 'Saída' pelo menu lateral Movimento → Requisição de Saída."""
    menu = frame.locator("div").filter(has_text=re.compile(r"^Requisição de Saída$")).first
    menu.wait_for(state="attached", timeout=TIMEOUT)
    if not menu.is_visible():
        frame.locator("div").filter(has_text=re.compile(r"^Movimento$")).first.click()
    menu.click()
    frame.get_by_role("button", name="Inserir", exact=True).wait_for(
        state="visible", timeout=TIMEOUT
    )
    aguardar_mascara(frame)


class ErroAberturaFormulario(ErroSCPI):
    """O formulário de inclusão não abriu. Nada foi preenchido nem salvo, então o lote pode
    recomeçar do zero depois de limpar a tela."""


TENTATIVAS_ABERTURA = 3


@contextmanager
def falha_de_abertura(descricao: str) -> Iterator[None]:
    """Converte o timeout de um passo da abertura em `ErroAberturaFormulario` (repetível).
    Só envolve cliques e esperas da abertura; as caixas de mensagem do SCPI ficam de fora."""
    from playwright.sync_api import TimeoutError as TimeoutPlaywright

    try:
        yield
    except TimeoutPlaywright as e:
        raise ErroAberturaFormulario(f"{descricao}: {resumo_erro(e)}") from e


def campo_da_abertura(frame: Frame, rotulo: str):
    """`campo` para a abertura do formulário: campo ainda ausente é falha de abertura
    (repetível), não erro do lote."""
    try:
        return campo(frame, rotulo)
    except ErroSCPI as e:
        raise ErroAberturaFormulario(str(e)) from e


ESPERA_MODO_INCLUSAO_MS = 6000
INTERVALO_MODO_INCLUSAO_MS = 250
CONSULTA_MODO_INCLUSAO_MS = 250  # teto de cada is_enabled: o laço consulta o campo de novo


def aguardar_modo_inclusao(frame: Frame) -> None:
    """O SCPI habilita os campos do formulário um instante depois de a máscara sumir: uma
    única conferência logo em seguida dava falso negativo (o print tirado 0,1 s depois do erro
    já mostrava o formulário em inclusão). Consulta por até `ESPERA_MODO_INCLUSAO_MS` antes de
    declarar que o formulário não entrou em modo de inclusão. Cada consulta espera no máximo
    `CONSULTA_MODO_INCLUSAO_MS` (o `is_enabled` espera 30 s por padrão se o SCPI trocar o input
    depois de achado o ID, e o laço não chegaria a consultar o novo; `timeout=0` desligaria o
    limite). O prazo de 6 s é nominal: o tempo restante é recalculado a cada volta, a pausa é
    limitada a ele e a última consulta, depois do prazo, pode somar até esse teto por campo."""
    from playwright.sync_api import Error as ErroPlaywright

    prazo = time.monotonic() + ESPERA_MODO_INCLUSAO_MS / 1000

    def restante_ms() -> float:
        return (prazo - time.monotonic()) * 1000

    def habilitado(rotulo: str) -> bool:
        return campo_da_abertura(frame, rotulo).is_enabled(timeout=CONSULTA_MODO_INCLUSAO_MS)

    while True:
        try:
            with falha_de_abertura("campos do formulário não apareceram"):
                habilitados = habilitado("Data e Hora da Saída") and habilitado("Recebimento")
        except ErroAberturaFormulario:
            habilitados = False  # campo ausente ou trocado: consulta de novo na próxima volta
        except ErroPlaywright as e:
            if "not attached to the DOM" not in str(e):
                raise
            habilitados = False  # o SCPI trocou o input durante a consulta
        if habilitados:
            return
        restante = restante_ms()
        if restante <= 0:
            break
        frame.page.wait_for_timeout(min(INTERVALO_MODO_INCLUSAO_MS, restante))
    raise ErroAberturaFormulario("formulário não entrou em modo de inclusão")


def abrir_formulario(frame: Frame) -> None:
    """Inserir → 'Nova Requisição de Saída' → Produto ▾ → Lançamento Manual."""
    with falha_de_abertura("aba 'Dados da Saída' não respondeu"):
        frame.get_by_role("tab", name="Dados da Saída").click()
    dialogo = janela(frame, "Nova Requisição de Saída")
    produto = dialogo.get_by_role("button", name="Produto", exact=True).first
    # logo após (re)abrir a tela o SCPI às vezes ignora o primeiro clique em Inserir
    for tentativa in range(3):
        with falha_de_abertura("botão Inserir não respondeu"):
            frame.get_by_role("button", name="Inserir", exact=True).click()
        try:
            produto.wait_for(state="visible", timeout=10000)
            break
        except Exception:
            if tentativa == 2:
                raise ErroAberturaFormulario(
                    "diálogo 'Nova Requisição de Saída' não abriu após 3 cliques em Inserir"
                ) from None
            checar_mensagem(frame, "abrir formulário")
    # split button: só a setinha (borda direita) abre o submenu; às vezes o SCPI ignora o
    # clique, ou o submenu aparece e fecha logo em seguida — por isso o clique no item
    # também fica dentro da repetição
    manual = frame.get_by_role("menuitem", name="Lançamento Manual").filter(visible=True).first
    for tentativa in range(3):
        try:
            if not manual.is_visible():
                caixa = produto.bounding_box()
                produto.click(position={"x": caixa["width"] - 8, "y": caixa["height"] / 2})
                manual.wait_for(state="visible", timeout=5000)
            manual.click(timeout=5000)
            break
        except Exception:
            if tentativa == 2:
                raise ErroAberturaFormulario(
                    "submenu 'Lançamento Manual' não abriu após 3 cliques em Produto ▾"
                ) from None
    aguardar_mascara(frame)
    # o SCPI às vezes responde com "Ajax Error" e deixa o formulário inconsistente
    checar_mensagem(frame, "abrir formulário")

    with falha_de_abertura("campos do formulário não apareceram"):
        data = campo_da_abertura(frame, "Data e Hora da Saída")
        data.wait_for(state="visible", timeout=TIMEOUT)
    aguardar_modo_inclusao(frame)


def preencher_cabecalho(frame: Frame, req: Requisicao) -> None:
    data = campo(frame, "Data e Hora da Saída")
    data.fill(req.data)
    sair_do_campo(frame, data, "data da saída")

    selecionar_combo(frame, "Tipo Saída", req.tipo_saida)

    # centro de custo ANTES dos itens: o SCPI replica para todos os itens. Centro de custo
    # de veículo preenche sozinho Placa/Motorista e pergunta se é saída de combustível
    cc = campo(frame, "Centro de Custo")
    cc.fill(req.cod_ccusto)
    sair_do_campo(frame, cc, "centro de custo")

    # sem Tab: no Recebimento o Tab pula para os itens e cria uma linha vazia
    receb = campo(frame, "Recebimento")
    receb.fill(req.recebedor)
    receb.dispatch_event("change")
    # "Interessado/Responsável" vem com o usuário logado. Tipo/Motivo e Observações da
    # planilha não vão para o SCPI


def ler_itens(frame: Frame) -> list[dict[str, str]]:
    itens = frame.evaluate(JS_LER_ITENS)
    if itens is None:
        raise ErroSCPI("grid 'Itens da Saída' não encontrado")
    return itens


# célula (linha do grid, coluna) cujo editor está com o foco, ou null
JS_CELULA_EM_EDICAO = """
() => {
    const a = document.activeElement;
    const cell = a && a.tagName === 'INPUT' ? a.closest('.x-grid-cell') : null;
    if (!cell) return null;
    const row = cell.closest('.x-grid-item');
    const rows = [...row.parentElement.closest('.x-grid').querySelectorAll('.x-grid-item')];
    return [rows.indexOf(row), cell.getAttribute('data-columnid')];
}
"""


def grid_itens(frame: Frame):
    return frame.locator(".x-grid").filter(has_text="Descrição do Produto/Serviço").first


# mesmo critério de JS_LER_ITENS (innerText do cabeçalho; o textContent traz lixo do ExtJS)
JS_ID_COLUNA = """
(coluna) => {
    const grid = [...document.querySelectorAll('.x-grid')].filter(g => g.offsetParent !== null)
        .find(g => g.innerText.includes('Descrição do Produto/Serviço'));
    const h = grid && [...grid.querySelectorAll('.x-column-header')]
        .find(h => h.innerText.trim() === coluna);
    return h ? h.id : null;
}
"""


def id_coluna(frame: Frame, coluna: str) -> str:
    col_id = frame.evaluate(JS_ID_COLUNA, coluna)
    if not col_id:
        raise ErroSCPI(f"coluna '{coluna}' não encontrada no grid de itens")
    return col_id


def celula_item(frame: Frame, linha: int, coluna: str):
    return (
        grid_itens(frame)
        .locator(".x-grid-item")
        .nth(linha)
        .locator(f'[data-columnid="{id_coluna(frame, coluna)}"]')
    )


def pausar(frame: Frame) -> None:
    """Espera `PAUSA_ENTRE_ACOES_MS` entre duas ações do preenchimento dos itens."""
    frame.page.wait_for_timeout(PAUSA_ENTRE_ACOES_MS)


def editar_celula(frame: Frame, linha: int, coluna: str):
    """Garante o editor aberto na célula (linha, coluna) e devolve o input. O SCPI às vezes
    avança o foco sozinho (Código → QTD), às vezes não — nesse caso abre com duplo clique."""
    alvo = [linha, id_coluna(frame, coluna)]
    if frame.evaluate(JS_CELULA_EM_EDICAO) != alvo:
        frame.page.keyboard.press("Escape")
        celula_item(frame, linha, coluna).dblclick()
        for _ in range(20):
            if frame.evaluate(JS_CELULA_EM_EDICAO) == alvo:
                break
            frame.page.wait_for_timeout(250)
        else:
            raise ErroSCPI(f"não consegui abrir a célula '{coluna}' da linha {linha + 1} do grid")
    return frame.locator("input:focus")


ESPERA_FOCO_MS = 5000  # por tentativa: o editor que perde o foco não volta sozinho
TENTATIVAS_CELULA = 3


def preencher_celula(frame: Frame, linha: int, coluna: str, valor: str, *, digitando: bool = False):
    """Abre o editor da célula e preenche. O SCPI às vezes redesenha a linha (o lookup do
    produto termina) entre a conferência do editor e o `fill`, e o editor fecha: sem foco, o
    `fill` esperaria 30 s e o lote inteiro cairia. Aqui cada tentativa espera pouco e, se o
    foco sumiu, reabre o editor e preenche de novo (o `fill` é idempotente). Com `digitando`, em vez
    do `fill` (que troca o conteúdo de uma vez) seleciona o conteúdo e digita tecla a tecla, como
    uma pessoa e como o código do produto. Devolve o input."""
    from playwright.sync_api import TimeoutError as TimeoutPlaywright

    for tentativa in range(1, TENTATIVAS_CELULA + 1):
        try:
            entrada = editar_celula(frame, linha, coluna)
            if digitando:
                entrada.press("ControlOrMeta+a", timeout=ESPERA_FOCO_MS)
                entrada.press_sequentially(valor, timeout=ESPERA_FOCO_MS)
            else:
                entrada.fill(valor, timeout=ESPERA_FOCO_MS)
            return entrada
        except (TimeoutPlaywright, ErroSCPI):
            if tentativa == TENTATIVAS_CELULA:
                raise
            log(
                f"  editor da célula '{coluna}' (linha {linha + 1}) não abriu ou perdeu o foco; "
                f"reabrindo ({tentativa}/{TENTATIVAS_CELULA})"
            )
            try:
                aguardar_mascara(frame)
            except TimeoutPlaywright:
                pass  # máscara ainda visível: a próxima tentativa decide


ESTABILIDADE_LINHA_MS = 400
LEITURAS_ESTAVEIS = 2
ESPERA_LINHA_ESTAVEL_MS = 10000
TENTATIVAS_QTD = 3


def aguardar_linha_estavel(frame: Frame, i: int, item: Item) -> bool:
    """Depois do Tab no código, o SCPI termina o lookup do produto de forma assíncrona e
    redesenha a linha (volta a QTD para 1 e fecha o editor). Espera a linha mostrar o produto
    e ficar igual em leituras seguidas antes de mexer na QTD. Devolve False se não estabilizou:
    quem chama segue, e a conferência da QTD decide."""
    anterior = None
    iguais = 0
    for _ in range(ESPERA_LINHA_ESTAVEL_MS // ESTABILIDADE_LINHA_MS):
        linhas = ler_itens(frame)
        atual = linhas[i] if i < len(linhas) else None
        pronta = bool(atual) and atual.get("Código") == item.cadpro
        pronta = pronta and bool(atual.get("Descrição do Produto/Serviço", "").strip())
        iguais = iguais + 1 if pronta and atual == anterior else 0
        if iguais >= LEITURAS_ESTAVEIS - 1 and pronta:
            return True
        anterior = atual
        frame.page.wait_for_timeout(ESTABILIDADE_LINHA_MS)
    return False


def qtd_confere(linha: dict[str, str], item: Item) -> bool:
    try:
        return parse_decimal_br(linha.get("QTD", "")) == Decimal(item.qtd.replace(",", "."))
    except InvalidOperation:
        return False


def definir_qtd(frame: Frame, i: int, item: Item, etapa: str) -> None:
    """Preenche a QTD e confere no grid; se o SCPI a devolveu ao padrão (redesenho tardio da
    linha), espera a linha estabilizar e preenche de novo. Depois das tentativas, deixa a
    divergência para `conferir_item`, que recusa o lote."""
    for tentativa in range(1, TENTATIVAS_QTD + 1):
        if not aguardar_linha_estavel(frame, i, item):
            # linha ausente ou com outro produto: preencher agora poderia gravar a QTD errada
            raise ErroSCPI(f"{etapa}: a linha do item não estabilizou no grid")
        qtd = preencher_celula(frame, i, "QTD", item.qtd, digitando=True)
        pausar(frame)
        qtd.press("Tab")
        pausar(frame)
        aguardar_mascara(frame)
        checar_mensagem(frame, etapa)
        frame.page.keyboard.press("Escape")
        pausar(frame)
        linhas = ler_itens(frame)
        if i < len(linhas) and qtd_confere(linhas[i], item):
            return
        if tentativa < TENTATIVAS_QTD:
            valor = linhas[i].get("QTD") if i < len(linhas) else None
            log(
                f"  QTD voltou para {valor!r} no grid; "
                f"preenchendo de novo ({tentativa}/{TENTATIVAS_QTD})"
            )


ESTABILIDADE_GRID_MS = 2000
INTERVALO_GRID_MS = 500
ESPERA_GRID_ESTAVEL_MS = 15000
RODADAS_RECONCILIACAO = 5


def aguardar_grid_estavel(frame: Frame) -> bool:
    """Espera o grid de itens ficar igual por `ESTABILIDADE_GRID_MS`. O SCPI responde aos
    lookups de forma assíncrona e uma resposta tardia pode redesenhar uma linha já conferida
    (a QTD volta a 1, como visto no AV-000094): só vale conferir o grid depois que ele parar
    de mudar. Devolve False se não estabilizou no tempo."""
    leituras_iguais = 0
    anterior = None
    leituras = ESTABILIDADE_GRID_MS // INTERVALO_GRID_MS
    for _ in range(ESPERA_GRID_ESTAVEL_MS // INTERVALO_GRID_MS):
        atual = ler_itens(frame)
        leituras_iguais = leituras_iguais + 1 if atual == anterior else 0
        if leituras_iguais >= leituras:
            return True
        anterior = atual
        frame.page.wait_for_timeout(INTERVALO_GRID_MS)
    return False


def linha_confere(linha: dict[str, str], item: Item) -> bool:
    """Código, QTD e (quando há) placa da linha do grid iguais ao pedido."""
    if linha.get("Código") != item.cadpro or not qtd_confere(linha, item):
        return False
    return not item.placa or norm_placa(linha.get("Placa (F9)", "")) == item.placa


def descrever_divergencias(linhas: list[dict[str, str]], itens: list[Item], indices) -> str:
    """ "item 5: QTD '1' (esperado 4)", para o log dizer o que o SCPI deixou no grid."""
    partes = []
    for i in indices:
        atual = linhas[i].get("QTD") if i < len(linhas) else None
        partes.append(f"item {i + 1}: QTD {atual!r} (esperado {itens[i].qtd})")
    return "; ".join(partes)


def registrar_regressoes(
    frame: Frame, req: Requisicao, ate: int, quando: str, vistos: set[int]
) -> None:
    """Só diagnóstico: as linhas já preenchidas (antes de `ate`) ainda mostram a QTD do pedido?
    O SCPI às vezes devolve uma QTD ao padrão (1) depois do preenchimento; o log diz em que
    momento, para achar o gatilho. Não altera nada."""
    linhas = ler_itens(frame)
    divergentes = [
        i
        for i in range(min(ate, len(req.itens)))
        if i >= len(linhas) or not qtd_confere(linhas[i], req.itens[i])
    ]
    novos = [i for i in divergentes if i not in vistos]
    vistos.update(divergentes)
    if novos:
        log(f"  ⚠ {quando}: {descrever_divergencias(linhas, req.itens, novos)}")


def instalar_diagnostico(frame: Frame) -> None:
    """Só diagnóstico: liga a escuta das recargas da grade. Nunca interrompe o lançamento."""
    try:
        if not frame.evaluate(JS_DIAGNOSTICO_INSTALAR):
            log("  diagnóstico do servidor indisponível: Ext não encontrado no frame")
    except Exception as e:
        log(f"  diagnóstico do servidor indisponível ({type(e).__name__})")


def registrar_servidor(frame: Frame, req: Requisicao, quando: str) -> None:
    """Só diagnóstico: loga o que o servidor devolveu nas recargas da grade desde a última
    leitura (código e QTD de cada linha, e se alguma QTD difere do pedido). Não altera nada nem
    levanta erro."""
    try:
        dados = frame.evaluate(JS_DIAGNOSTICO_LER)
    except Exception:
        return
    for linhas in dados:
        resumo = " ".join(f"{i + 1}:{cod} x{qtd}" for i, (cod, qtd, _) in enumerate(linhas))
        log(f"  🔎 {quando}: o SCPI recarregou a grade do servidor [{resumo}]")
        for i, (cod, qtd, _) in enumerate(linhas[: len(req.itens)]):
            if not str(cod or "").strip():
                continue  # linha nova, ainda sem código
            esperado = Decimal(req.itens[i].qtd.replace(",", "."))
            try:
                diverge = Decimal(str(qtd)) != esperado
            except InvalidOperation:
                diverge = True
            if diverge:
                log(f"  ⚠ servidor devolveu QTD {qtd} no item {i + 1} (pedido: {esperado})")


def recarregar_grade(frame: Frame) -> bool:
    """Faz a grade mostrar o que o SERVIDOR tem. A tela só se atualiza a partir do servidor no
    "Novo Item": uma QTD que o servidor perdeu na última linha continuaria certa na tela, e a
    conferência final a deixaria passar. Devolve False se não recarregou (quem chama recusa o
    lote)."""
    try:
        recarregou = bool(frame.evaluate(JS_RECARREGAR_GRADE))
    except Exception as e:
        log(f"  ⚠ não consegui recarregar a grade do servidor ({type(e).__name__})")
        return False
    if not recarregou:
        log("  ⚠ a grade não recarregou do servidor")
    return recarregou


def reconciliar_itens(frame: Frame, req: Requisicao) -> None:
    """Última barreira antes de salvar: com o grid estável, confere TODAS as linhas contra o
    pedido; as que divergirem (QTD devolvida ao padrão por uma resposta tardia do SCPI) são
    preenchidas de novo, por algumas rodadas. Se ainda divergir, o lote falha (`ErroSCPI`) e
    nada é salvo: o `conferir_item` de cada linha acontece cedo demais para pegar isso."""
    total = len(req.itens)
    for rodada in range(1, RODADAS_RECONCILIACAO + 1):
        if not recarregar_grade(frame):
            # sem a leitura do servidor, a tela pode mostrar uma QTD que ele não tem
            raise ErroSCPI(
                f"conferência final: não foi possível recarregar a grade do servidor "
                f"({rodada}/{RODADAS_RECONCILIACAO})"
            )
        if not aguardar_grid_estavel(frame):
            # uma leitura que coincide com o pedido não vale com o SCPI ainda mexendo no grid
            raise ErroSCPI(
                f"conferência final: grid não estabilizou ({rodada}/{RODADAS_RECONCILIACAO})"
            )
        registrar_servidor(frame, req, f"conferência final ({rodada}/{RODADAS_RECONCILIACAO})")
        linhas = ler_itens(frame)
        # as linhas esperadas podem ser só o começo do grid: uma linha a mais seria salva junto
        codificadas = [linha for linha in linhas if RE_CADPRO.match(linha.get("Código", ""))]
        if len(codificadas) != total:
            raise ErroSCPI(
                f"conferência final: grid tem {len(codificadas)} item(ns), esperado {total}"
            )
        divergentes = [
            i
            for i, item in enumerate(req.itens)
            if i >= len(linhas) or not linha_confere(linhas[i], item)
        ]
        if not divergentes:
            log(f"  conferência final: {total} item(ns) do grid iguais ao pedido")
            return
        if rodada == RODADAS_RECONCILIACAO:
            break
        log(
            f"  conferência final: item(ns) {[i + 1 for i in divergentes]} divergem do pedido "
            f"({descrever_divergencias(linhas, req.itens, divergentes)}); "
            f"corrigindo ({rodada}/{RODADAS_RECONCILIACAO})"
        )
        for i in divergentes:
            item = req.itens[i]
            definir_qtd(frame, i, item, f"item {i + 1}/{total} ({item.cadpro})")
    for i, item in enumerate(req.itens):  # levanta o erro específico da primeira divergência
        conferir_item(
            frame, i, item, req, f"item {i + 1}/{total} ({item.cadpro}) na conferência final"
        )
    raise ErroSCPI("conferência final: os itens do grid continuam divergindo do pedido")


def adicionar_itens(frame: Frame, req: Requisicao) -> None:
    frame.get_by_role("tab", name="Itens da Saída").click()
    pausar(frame)
    aguardar_mascara(frame)
    novo_item = frame.get_by_role("button", name=re.compile(r"Novo Item"))
    vistos: set[int] = set()  # linhas já registradas como devolvidas ao padrão (log de diagnóstico)
    instalar_diagnostico(frame)

    for i, item in enumerate(req.itens):
        etapa = f"item {i + 1}/{len(req.itens)} ({item.cadpro})"
        log(f"  {etapa}: qtd {item.qtd}" + (f", placa {item.placa}" if item.placa else ""))
        try:
            registrar_regressoes(frame, req, i, f"ao começar o item {i + 1}", vistos)
            linhas = ler_itens(frame)
            # reaproveita linha vazia já criada pelo SCPI; senão cria uma
            if not (len(linhas) > i and not RE_CADPRO.match(linhas[i].get("Código", ""))):
                novo_item.click()
                pausar(frame)
                aguardar_mascara(frame)
                registrar_regressoes(frame, req, i, f"depois do Novo Item do item {i + 1}", vistos)
                registrar_servidor(frame, req, f"depois do Novo Item do item {i + 1}")
            # a máscara ___.___.___ do Código aceita só os dígitos
            codigo = editar_celula(frame, i, "Código")
            pausar(frame)
            codigo.press_sequentially(item.cadpro.replace(".", ""))
            pausar(frame)
            codigo.press("Tab")
            pausar(frame)
            aguardar_mascara(frame)
            checar_mensagem(frame, etapa)
            registrar_regressoes(frame, req, i, f"depois do código do item {i + 1}", vistos)

            definir_qtd(frame, i, item, etapa)

            # centro de custo de veículo já preenche a placa no item
            if item.placa and norm_placa(ler_itens(frame)[i].get("Placa (F9)", "")) != item.placa:
                placa = preencher_celula(frame, i, "Placa (F9)", item.placa)
                pausar(frame)
                sair_do_campo(frame, placa, f"{etapa} placa")
                pausar(frame)
                frame.page.keyboard.press("Escape")  # sai do hodômetro "Atual" sem alterar
                pausar(frame)
        except ErroSCPI:
            raise
        except Exception as e:
            raise ErroSCPI(f"{etapa}: {resumo_erro(e)}") from e

        conferir_item(frame, i, item, req, etapa)
        registrar_regressoes(frame, req, i + 1, f"depois de conferir o item {i + 1}", vistos)
        registrar_servidor(frame, req, f"depois de conferir o item {i + 1}")

    # confere que o grid tem exatamente os itens esperados antes de salvar
    linhas_grid = [r for r in ler_itens(frame) if RE_CADPRO.match(r.get("Código", ""))]
    if len(linhas_grid) != len(req.itens):
        raise ErroSCPI(f"grid de itens tem {len(linhas_grid)} linha(s), esperado {len(req.itens)}")
    reconciliar_itens(frame, req)


def conferir_item(frame: Frame, i: int, item: Item, req: Requisicao, etapa: str) -> None:
    """Valida o que o SCPI carregou na linha do grid — inclusive saldo, que o SCPI não checa."""
    linhas = ler_itens(frame)
    if i >= len(linhas):
        raise ErroSCPI(f"{etapa}: linha não apareceu no grid")
    r = linhas[i]
    if r.get("Código") != item.cadpro:
        raise ErroSCPI(f"{etapa}: grid mostra código '{r.get('Código')}'")
    try:
        qtd_grid = parse_decimal_br(r.get("QTD", ""))
        estoque = parse_decimal_br(r.get("Est. Atual", ""))
    except InvalidOperation:
        raise ErroSCPI(
            f"{etapa}: QTD/estoque ilegíveis no grid ({r.get('QTD')!r}, {r.get('Est. Atual')!r})"
        ) from None
    if qtd_grid != Decimal(item.qtd.replace(",", ".")):
        raise ErroSCPI(f"{etapa}: grid mostra QTD {r.get('QTD')}, esperado {item.qtd}")
    if qtd_grid > estoque:
        raise ErroSCPI(
            f"{etapa}: saldo insuficiente (pedido {item.qtd}, estoque {r.get('Est. Atual')})"
        )
    if r.get("C.Custo") != req.cod_ccusto:
        raise ErroSCPI(f"{etapa}: C.Custo do item '{r.get('C.Custo')}', esperado {req.cod_ccusto}")
    if item.placa and (norm_placa(r.get("Placa (F9)", "")) != item.placa or not r.get("Veículo")):
        raise ErroSCPI(f"{etapa}: placa '{item.placa}' não reconhecida pelo SCPI")
    log(
        f"    ok: {r.get('Descrição do Produto/Serviço')} | QTD {r.get('QTD')}"
        f" | estoque {r.get('Est. Atual')}"
        f" | c.custo {r.get('C.Custo')}" + (f" | {r.get('Veículo')}" if item.placa else "")
    )


def conferir_cabecalho(frame: Frame, req: Requisicao) -> None:
    """Relê o cabeçalho depois dos itens — o SCPI pode ter alterado algo nos lookups."""
    frame.get_by_role("tab", name="Dados da Saída").click()
    esperado = {
        "Data e Hora da Saída": req.data,
        "Tipo Saída": req.tipo_saida,
        "Centro de Custo": req.cod_ccusto,
        "Recebimento": req.recebedor,
    }
    for rotulo, valor in esperado.items():
        atual = campo(frame, rotulo).input_value()
        if norm(atual) != norm(valor):
            raise ErroSCPI(f"cabeçalho: '{rotulo}' ficou '{atual}', esperado '{valor}'")
    log("    ok: cabeçalho " + " | ".join(f"{k} = {v}" for k, v in esperado.items()))


# a tela "Saída" é ela mesma uma .x-window embutida; janelas flutuantes (pesquisa,
# manutenção preventiva, impressão) têm a classe x-layer — o botão do formulário é o
# x-btn cuja janela mais próxima NÃO é flutuante
XPATH_BOTOES_FORMULARIO = (
    "xpath=//a[contains(concat(' ',@class,' '),' x-btn ')]"
    "[ancestor::*[contains(concat(' ',@class,' '),' x-window ')][1]"
    "[not(contains(concat(' ',@class,' '),' x-layer '))]]"
)


def botao_formulario(frame: Frame, nome: str):
    """Botão visível da tela 'Saída' (há cópias com o mesmo nome em janelas flutuantes)."""
    return frame.locator(XPATH_BOTOES_FORMULARIO).filter(
        visible=True, has_text=re.compile(rf"^\s*{re.escape(nome)}\s*$")
    )


def botao_habilitado(botao) -> bool:
    return botao.count() == 1 and "x-btn-disabled" not in (botao.get_attribute("class") or "")


def localizar_salvar(frame: Frame):
    """Chamado ANTES da trava: se o botão não estiver pronto, é erro seguro (nada lançado)."""
    salvar = botao_formulario(frame, "Salvar")
    if salvar.count() != 1:
        raise ErroSCPI(f"esperado 1 botão Salvar visível na tela, encontrado {salvar.count()}")
    if not botao_habilitado(salvar):
        raise ErroSCPI("botão Salvar desabilitado")
    return salvar


def salvar_requisicao(frame: Frame, salvar) -> str:
    """Clique final em Salvar. Retorna o nº REQUI assim que ele aparece no formulário.
    Qualquer exceção aqui é resultado incerto."""
    salvar.click(timeout=10000)
    for _ in range(60):
        numero = RE_REQUI.search(frame.evaluate(JS_NUMERO_REQUISICAO) or "")
        if numero:
            return numero.group(1)
        msg = mensagem_scpi(frame)
        if msg and "sucesso" not in msg["texto"].lower():
            raise ResultadoIncerto(
                f"SCPI respondeu ao Salvar: '{' '.join(msg['texto'].split())}' {msg['botoes']}"
            )
        frame.page.wait_for_timeout(1000)
    raise ResultadoIncerto("número da requisição não apareceu após Salvar")


def fechar_janelas_pos_salvar(frame: Frame) -> None:
    """Manutenção Preventiva (por item com veículo) → Cancelar / OK / Sair;
    Imprimir Requisições → Sair. A requisição já está gravada aqui."""
    for _ in range(30):
        msg = mensagem_scpi(frame)
        if msg and "OK" in msg["botoes"]:
            log(f"  SCPI: {' '.join(msg['texto'].split())}")
            responder_mensagem(frame, "OK")
            continue
        titulos = frame.evaluate(JS_JANELAS)
        if "Controle de Manutenção Preventiva" in titulos:
            jan = janela(frame, "Controle de Manutenção Preventiva")
            cancelar = (
                jan.get_by_role("button", name="Cancelar", exact=True).filter(visible=True).last
            )
            botao = (
                cancelar
                if botao_habilitado(cancelar)
                else jan.get_by_role("button", name="Sair", exact=True).filter(visible=True).last
            )
            botao.click()
            aguardar_mascara(frame)
            continue
        if "Imprimir Requisições" in titulos:
            janela(frame, "Imprimir Requisições").get_by_role(
                "button", name="Sair", exact=True
            ).filter(visible=True).last.click()
            aguardar_mascara(frame)
            return
        frame.page.wait_for_timeout(1000)


def dialogo_nova_requisicao_aberto(frame: Frame) -> bool:
    """O diálogo 'Nova Requisição de Saída' é modal: aberto, cobre a tela inteira, mas o
    Playwright ainda vê Inserir habilitado atrás dele."""
    return janela(frame, "Nova Requisição de Saída").is_visible()


def cancelar_formulario(frame: Frame) -> None:
    """Descarta o formulário aberto para voltar a um estado limpo. Fechar o diálogo 'Nova
    Requisição de Saída' com Escape deixa a tela em modo de inclusão só um instante depois,
    por isso repete até Salvar desabilitado, Inserir habilitado e nenhum diálogo aberto (um
    diálogo esquecido bloqueia todo o lote seguinte)."""
    inserir = frame.get_by_role("button", name="Inserir", exact=True).filter(visible=True).first
    for _ in range(3):
        for _ in range(3):
            msg = mensagem_scpi(frame)
            if msg and "OK" in msg["botoes"]:
                responder_mensagem(frame, "OK")
            frame.page.keyboard.press("Escape")
        aguardar_mascara(frame)
        frame.page.wait_for_timeout(1500)
        cancelar = botao_formulario(frame, "Cancelar")
        if botao_habilitado(cancelar):
            cancelar.click()
            sim = frame.locator(".x-message-box").get_by_role("button", name="Sim", exact=True)
            sim.wait_for(state="visible", timeout=TIMEOUT)  # "Você Realmente Deseja Cancelar ?"
            sim.click()
            aguardar_mascara(frame)
            frame.page.wait_for_timeout(1000)
        # fora do modo de inclusão o Salvar fica desabilitado e o Inserir habilitado
        if (
            not botao_habilitado(botao_formulario(frame, "Salvar"))
            and botao_habilitado(inserir)
            and not dialogo_nova_requisicao_aberto(frame)
        ):
            return
    raise ErroSCPI("formulário continua em modo de inclusão após Cancelar")


class Sessao:
    """Mantém contexto/página/frame e permite recomeçar do zero se o SCPI travar."""

    def __init__(self, playwright):
        self.playwright = playwright
        self.context = None
        self.page: Page | None = None
        self.frame: Frame | None = None

    def abrir(self) -> None:
        self.context, self.page = abrir_sessao(
            self.playwright, settings.SCPI_PERFIL_DIR / "lancamento"
        )
        self.frame = frame_compras(self.page)
        abrir_tela_saida(self.frame)

    def fechar(self) -> None:
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None

    def reabrir_modulo(self) -> None:
        """Depois de salvar, o SCPI esvazia o iframe do Compras: Fechar → COMPRAS resolve
        sem novo login."""
        log("  reabrindo módulo Compras")
        self.page.get_by_role("button", name="Fechar", exact=True).click()
        self.page.get_by_text("COMPRAS", exact=True).wait_for(state="visible", timeout=TIMEOUT)
        self.frame = frame_compras(self.page)
        abrir_tela_saida(self.frame)

    def reiniciar(self) -> None:
        log("  reabrindo sessão SCPI do zero")
        self.fechar()
        self.abrir()

    def limpar(self) -> None:
        """Volta a um estado limpo: cancela o formulário; se não der, reabre o módulo; se
        não der, reabre a sessão."""
        for passo in (lambda: cancelar_formulario(self.frame), self.reabrir_modulo, self.reiniciar):
            try:
                passo()
                return
            except Exception as e:
                log(f"  limpeza falhou ({resumo_erro(e)}); tentando o próximo passo")
        raise RuntimeError("não foi possível voltar a um estado limpo no SCPI")


# ---------------------------------------------------------------- protocolo do lançamento


class NavegadorSCPI(Sessao):
    """O `scpi.lancamento.SCPI` sobre o Playwright. Cada método é um pedaço do `processar` do
    original; a trava no banco entre `preencher` e `salvar` fica em `scpi.lancamento`."""

    def __init__(self, playwright):
        super().__init__(playwright)
        self._salvar = None

    @staticmethod
    def _registrar_mensagem_scpi(frame: Frame) -> None:
        """Loga a caixa de mensagem aberta antes de a limpeza a fechar com OK. Não usa
        `checar_mensagem`, que levantaria erro e cortaria a repetição."""
        try:
            msg = mensagem_scpi(frame)
        except Exception:
            return
        if msg:
            log(f"  SCPI exibiu '{' '.join(msg['texto'].split())}' antes da limpeza")

    def preencher(self, req: Requisicao) -> None:
        frame = self.frame
        try:
            log("  etapa: abrir formulário")
            for tentativa in range(1, TENTATIVAS_ABERTURA + 1):
                try:
                    abrir_formulario(frame)
                    break
                except ErroAberturaFormulario as e:
                    if tentativa == TENTATIVAS_ABERTURA:
                        raise
                    log(
                        f"  {e}; limpando a tela e tentando de novo "
                        f"({tentativa}/{TENTATIVAS_ABERTURA})"
                    )
                    self._registrar_mensagem_scpi(frame)
                    self.limpar()
                    frame = self.frame  # a limpeza pode ter reaberto o módulo
            log(
                f"  etapa: cabeçalho (data {req.data}, tipo {req.tipo_saida}, "
                f"c.custo {req.cod_ccusto})"
            )
            preencher_cabecalho(frame, req)
            log("  etapa: itens")
            adicionar_itens(frame, req)
            conferir_cabecalho(frame, req)
            self._salvar = localizar_salvar(frame)
        except ErroSCPI:
            raise
        except Exception as e:
            raise ErroSCPI(f"{resumo_erro(e)}") from e

    def salvar(self) -> str:
        try:
            log("  etapa: salvar no SCPI")
            return salvar_requisicao(self.frame, self._salvar)
        except ResultadoIncerto:
            raise
        except Exception as e:
            raise ResultadoIncerto(f"{resumo_erro(e)}") from e

    def depois_de_salvar(self) -> None:
        try:
            fechar_janelas_pos_salvar(self.frame)
        except Exception as e:
            log(f"  ⚠ janelas pós-salvar ({type(e).__name__}); seguindo com a reabertura do módulo")
        self.reabrir_modulo()

    def encerrar_simulacao(self) -> None:
        log("  [DRY-RUN] formulário preenchido e conferido — NÃO clicado em Salvar")
        self.limpar()

    def descartar(self, lote: str) -> None:
        momento = timezone.localtime()
        caminho = Path(settings.LOG_DIR) / f"scpi-lancamento-{lote}-{momento:%Y%m%d_%H%M%S}.png"
        try:
            self.page.screenshot(path=str(caminho))
            log(f"  print da tela: {caminho}")
        except Exception:
            log(f"  não foi possível salvar o print da tela em {caminho}")
        self.limpar()


@contextmanager
def navegador() -> Iterator[NavegadorSCPI]:
    """Abre o Playwright, entra no SCPI até a tela de saída e fecha tudo no fim. O lançamento
    grava no banco com o navegador aberto, então o ORM fica liberado (`orm_liberado`)."""
    from playwright.sync_api import sync_playwright

    with orm_liberado(), sync_playwright() as playwright:
        sessao = NavegadorSCPI(playwright)
        try:
            sessao.abrir()
            yield sessao
        finally:
            sessao.fechar()
