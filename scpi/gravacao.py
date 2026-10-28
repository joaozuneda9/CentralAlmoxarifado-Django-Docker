"""Gravação no banco das linhas lidas dos CSVs do SCPI.

Cada função roda dentro da transação aberta por `scpi.execucao.executar`: uma
`ErroImportacao` desfaz tudo e os dados anteriores continuam valendo.
"""

from collections import Counter
from datetime import date, timedelta

from django.db.models import Max
from django.utils import timezone

from catalogo.models import Importacao, Material, SaidaSCPI
from pedidos.regras import norm_u
from scpi.execucao import Resultado
from scpi.leitura import ErroImportacao, Leitura

# Fração máxima dos materiais visíveis que pode sumir do cadastro numa importação; acima
# disso o CSV provavelmente veio cortado e a importação aborta (salvo --forcar).
LIMITE_SUMIDOS = 0.2

CAMPOS_TEXTO = ("nome", "unidade", "grupo", "subgrupo")
CAMPOS_CADASTRO = [*CAMPOS_TEXTO, "oculto", "duplicado"]
LOTE = 1000

# Cada importação de saídas volta estes dias antes do fim da anterior: o robô lança saídas com
# a data efetiva do atendimento, que pode ser anterior à última importação. A chave única
# (id_requi, cadpro) evita duplicar o que já veio.
SOBREPOSICAO_SAIDAS = timedelta(days=7)

# O cadastro incremental também volta alguns dias antes do corte da carga anterior: um material
# cadastrado perto do corte pode não ter entrado. O código é a chave, então repetir não duplica.
SOBREPOSICAO_CADASTRO = timedelta(days=7)


def lista_curta(itens: list[str], limite: int = 8) -> str:
    """'a, b, c' ou, passando do limite, os primeiros seguidos de 'e mais N'."""
    if len(itens) <= limite:
        return ", ".join(itens)
    return f"{', '.join(itens[:limite])} e mais {len(itens) - limite}"


def _max(campo: str) -> int:
    return Material._meta.get_field(campo).max_length


def chave(codigo: str) -> str:
    """Código como o banco o compara: a collation (utf8mb4_unicode_ci) ignora maiúsculas,
    acentos e espaços no fim, então '0-a' e '0-A' são o mesmo material."""
    return norm_u(codigo)


def gravar_cadastro(leitura: Leitura, forcar: bool = False, parcial: bool = False) -> Resultado:
    """Grava o cadastro.

    Completo (o padrão): quem sumiu do CSV fica oculto, e um CSV que tiraria mais de 20% dos
    visíveis é recusado (salvo `forcar`). `parcial`, para o CSV de só um período do cadastro:
    grava apenas o que o CSV traz e não oculta nem recusa nada, porque o que está fora do
    período não é "sumido".
    """
    avisos = list(leitura.avisos)
    novos = {}
    repetidos: list[str] = []
    for linha in leitura.linhas:
        if len(linha.codigo) > _max("codigo"):
            avisos.append(
                f"Código com mais de {_max('codigo')} caracteres ignorado: {linha.codigo}."
            )
        elif chave(linha.codigo) in novos:
            if linha.codigo not in repetidos:
                repetidos.append(linha.codigo)
        else:
            novos[chave(linha.codigo)] = linha
    if not novos:
        if parcial:
            # Nenhum material cadastrado no período: comum no "só os novos" de uma semana parada.
            return Resultado(0, avisos)
        raise ErroImportacao("Cadastro: o CSV não tem nenhum material; nada foi alterado.")

    # Todos, mesmo na importação parcial: o banco compara o código pela collation (maiúsculas,
    # acentos, espaço no fim) e `chave()` também colapsa espaços internos; um filtro `codigo__in`
    # com os códigos do CSV não acharia '0-A  B' para '0-A B' e criaria um segundo material.
    existentes = {chave(m.codigo): m for m in Material.objects.only("codigo", *CAMPOS_CADASTRO)}
    visiveis = [c for c, m in existentes.items() if not m.oculto]
    sumidos = [] if parcial else [c for c in visiveis if c not in novos]
    if visiveis and len(sumidos) > LIMITE_SUMIDOS * len(visiveis) and not forcar:
        raise ErroImportacao(
            f"Cadastro: o CSV não traz {len(sumidos)} dos {len(visiveis)} materiais visíveis "
            "(mais de 20%). Nada foi alterado; confira o relatório do SCPI ou rode com --forcar."
        )
    if repetidos:
        avisos.append(f"Códigos repetidos no cadastro (bloqueados): {lista_curta(repetidos)}.")
    chaves_repetidas = {chave(c) for c in repetidos}

    criar, atualizar = [], []
    for c, linha in novos.items():
        valores = {"oculto": linha.oculto, "duplicado": c in chaves_repetidas}
        for campo in CAMPOS_TEXTO:
            texto, limite = getattr(linha, campo), _max(campo)
            if len(texto) > limite:
                avisos.append(f"Texto cortado em {campo} ({limite} caracteres): {linha.codigo}.")
                texto = texto[:limite]
            valores[campo] = texto
        material = existentes.get(c)
        if material is None:
            criar.append(Material(codigo=linha.codigo, **valores))
        elif any(getattr(material, campo) != valor for campo, valor in valores.items()):
            for campo, valor in valores.items():
                setattr(material, campo, valor)
            atualizar.append(material)

    Material.objects.bulk_create(criar, batch_size=LOTE)
    Material.objects.bulk_update(atualizar, CAMPOS_CADASTRO, batch_size=LOTE)
    Material.objects.filter(pk__in=[existentes[c].pk for c in sumidos]).update(oculto=True)
    return Resultado(len(novos), avisos)


def gravar_estoque(leitura: Leitura, em) -> Resultado:
    """Substitui todos os saldos: código ausente do CSV fica com estoque 0."""
    if not leitura.linhas:
        raise ErroImportacao("Estoque: o CSV não tem nenhum material; nada foi alterado.")
    avisos = list(leitura.avisos)
    saldos, codigos, repetidos = {}, {}, []
    for linha in leitura.linhas:
        c = chave(linha.codigo)
        if c in saldos and linha.codigo not in repetidos:
            repetidos.append(linha.codigo)
        saldos[c] = linha.qtd
        codigos[c] = linha.codigo
    if repetidos:
        avisos.append(
            f"Códigos repetidos no estoque (vale a última linha): {lista_curta(repetidos)}."
        )

    Material.objects.update(estoque=0, estoque_em=em)
    materiais = [
        m
        for m in Material.objects.filter(codigo__in=codigos.values()).only("codigo", "estoque")
        if chave(m.codigo) in saldos
    ]
    for material in materiais:
        material.estoque = saldos[chave(material.codigo)]
    Material.objects.bulk_update(materiais, ["estoque"], batch_size=LOTE)

    cadastrados = {chave(m.codigo) for m in materiais}
    sem_cadastro = [codigos[c] for c in saldos if c not in cadastrados]
    if sem_cadastro:
        avisos.append(f"Códigos com saldo sem cadastro (ignorados): {lista_curta(sem_cadastro)}.")
    return Resultado(len(materiais), avisos)


def periodo_cadastro_padrao(hoje: date) -> tuple[date, date] | None:
    """Período do cadastro incremental: do corte da última carga bem-sucedida (menos a
    sobreposição) até hoje. O corte de uma importação parcial é o fim do seu período; o de uma
    completa (por exemplo, o CSV da carga inicial) é o dia em que ela terminou. None se ainda não
    há nenhuma carga: então só o cadastro inteiro serve."""
    sucessos = Importacao.objects.filter(
        tipo=Importacao.Tipo.CADASTRO, situacao=Importacao.Situacao.SUCESSO
    )
    # A data do fim da carga completa é calculada aqui, não no banco: a conversão de fuso do
    # MySQL/MariaDB devolve vazio quando as tabelas de fuso horário não estão carregadas.
    fim_completa = sucessos.filter(periodo_ate__isnull=True).aggregate(m=Max("fim"))["m"]
    cortes = [
        sucessos.aggregate(m=Max("periodo_ate"))["m"],
        timezone.localtime(fim_completa).date() if fim_completa else None,
    ]
    cortes = [c for c in cortes if c]
    if not cortes:
        return None
    return min(max(cortes) - SOBREPOSICAO_CADASTRO, hoje), hoje


def periodo_saidas(
    hoje: date, desde: date | None = None, ate: date | None = None
) -> tuple[date, date]:
    """Intervalo da próxima importação de saídas (veja `SOBREPOSICAO_SAIDAS`)."""
    fim = ate or hoje
    inicio = desde
    if inicio is None:
        # O maior fim entre os sucessos, não o da última execução: uma carga histórica feita
        # depois (--ate no passado) não pode fazer o período automático recuar.
        ultimo_fim = Importacao.objects.filter(
            tipo=Importacao.Tipo.SAIDAS, situacao=Importacao.Situacao.SUCESSO
        ).aggregate(m=Max("periodo_ate"))["m"]
        inicio = ultimo_fim - SOBREPOSICAO_SAIDAS if ultimo_fim else date(hoje.year, 1, 1)
    if inicio > fim:
        raise ErroImportacao(
            f"Saídas do SCPI: o início do período ({inicio:%d/%m/%Y}) é depois do fim "
            f"({fim:%d/%m/%Y})."
        )
    return inicio, fim


def gravar_saidas(leitura: Leitura) -> Resultado:
    """Acrescenta as saídas novas; as que já existem (id_requi, cadpro, item) ficam como estão.

    Cada linha do relatório é uma saída: o mesmo material repetido na requisição (outra placa,
    outro destino) ganha o item seguinte, na ordem do relatório."""
    itens: Counter = Counter()
    saidas = []
    for linha in leitura.linhas:
        c = (linha.id_requi, chave(linha.cadpro))
        itens[c] += 1
        saidas.append(
            SaidaSCPI(
                id_requi=linha.id_requi,
                cadpro=linha.cadpro,
                item=itens[c],
                data=linha.data,
                qtd=linha.qtd,
                valor=linha.valor,
            )
        )
    avisos = list(leitura.avisos)
    antes = SaidaSCPI.objects.count()
    SaidaSCPI.objects.bulk_create(saidas, batch_size=LOTE, ignore_conflicts=True)
    return Resultado(SaidaSCPI.objects.count() - antes, avisos)
