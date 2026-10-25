import unicodedata

from django.db import migrations, transaction

# Configuração das opções por formulário (spec 009), parte 2: os dados. Esta migration transcreve para
# as tabelas novas o que cada formulário oferecia por regra escrita no código, **sem mudar o que
# nenhum formulário oferece**, e confere o resultado no próprio banco: se a transcrição não
# reproduzir a regra antiga, a migration não conclui (FR-037, FR-038). Nada é apagado nem alterado
# nos cadastros antigos (`equipe_manutencao`, `MaterialOficina`, `MaterialEpi`).

CENTRO_OFICINA = "OFICINA MECÂNICA"
FORMULARIOS_TODOS = ("LIMPEZA", "AB", "EPIS")


def _norm(valor):
    """Como `regras.norm_u`: sem acento, em maiúsculas, espaços colapsados (copiado: a migration
    não depende de código do app que possa mudar depois)."""
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    sem_acento = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


def _linha_da_oficina(CentroCusto):
    """A linha sem placa de OFICINA MECÂNICA (a primeira por código), ou None."""
    for c in CentroCusto.objects.filter(placa__isnull=True).order_by("codigo"):
        if _norm(c.descricao) == _norm(CENTRO_OFICINA):
            return c
    return None


def _destinos(linhas, modo):
    """O que o formulário oferece como destino (`regras.opcoes_destino`), por modo: `padrao` (a
    descrição e, com placa, "descrição — placa"), `sem_placa` (uma por descrição) e `oficina` (a
    linha com placa só como "descrição — placa"). `linhas` são tuplas (descrição, código, placa)."""
    if modo == "sem_placa":
        return list(dict.fromkeys(d for d, _, _ in linhas))
    so_placa = modo == "oficina"
    descricoes = dict.fromkeys(d for d, _, p in linhas if not (so_placa and p))
    com_placa = dict.fromkeys(f"{d} — {p}" for d, _, p in linhas if p)
    return [*descricoes, *com_placa]


def _regra_antiga(apps):
    """Os destinos de cada formulário pela regra escrita no código antes da spec 009."""
    CentroCusto = apps.get_model("catalogo", "CentroCusto")
    todas = [(c.descricao, c.codigo, c.placa) for c in CentroCusto.objects.order_by("descricao", "placa")]
    equipe = [
        (c.descricao, c.codigo, None)
        for c in CentroCusto.objects.filter(equipe_manutencao=True).order_by("descricao", "codigo")
    ]
    oficina = _linha_da_oficina(CentroCusto)
    linhas_oficina = ([(oficina.descricao, oficina.codigo, None)] if oficina else []) + [
        (c.descricao, c.codigo, c.placa)
        for c in CentroCusto.objects.filter(placa__isnull=False).order_by("descricao", "placa")
    ]
    return {
        "LIMPEZA": _destinos(todas, "padrao"),
        "AB": _destinos(todas, "padrao"),
        "EPIS": _destinos(todas, "padrao"),
        "VIATURAS": _destinos(equipe, "sem_placa"),
        "OFICINA": _destinos(linhas_oficina, "oficina"),
    }


def _regra_nova(apps):
    """Os destinos de cada formulário pela tabela nova, com o mesmo modo de apresentação."""
    CentroFormulario = apps.get_model("catalogo", "CentroFormulario")
    modos = {
        "LIMPEZA": "padrao",
        "AB": "padrao",
        "EPIS": "padrao",
        "VIATURAS": "sem_placa",
        "OFICINA": "oficina",
    }
    destinos = {}
    for formulario, modo in modos.items():
        linhas = [
            (cf.centro.descricao, cf.centro.codigo, cf.centro.placa)
            for cf in CentroFormulario.objects.filter(formulario=formulario, centro__ativo=True)
            .select_related("centro")
            .order_by("centro__descricao", "centro__placa", "centro__codigo")
        ]
        destinos[formulario] = _destinos(linhas, modo)
    return destinos


def conferir(apps):
    """Levanta erro se a tabela nova não reproduz o que cada formulário oferecia (FR-038)."""
    antiga, nova = _regra_antiga(apps), _regra_nova(apps)
    for formulario, esperados in antiga.items():
        if sorted(esperados) != sorted(nova[formulario]):
            raise RuntimeError(
                f"Configuração dos formulários: a transcrição de {formulario} não reproduz a regra "
                f"antiga (esperado {sorted(esperados)}, obtido {sorted(nova[formulario])}). "
                "Nada foi alterado; é preciso uma decisão antes de seguir."
            )
    ExcecaoMaterial = apps.get_model("catalogo", "ExcecaoMaterial")
    for formulario, modelo in (("OFICINA", "MaterialOficina"), ("EPIS", "MaterialEpi")):
        avulsos = set(apps.get_model("catalogo", modelo).objects.values_list("material_id", flat=True))
        acrescentados = set(
            ExcecaoMaterial.objects.filter(formulario=formulario, habilitado=True).values_list(
                "material_id", flat=True
            )
        )
        if not avulsos <= acrescentados:
            raise RuntimeError(
                f"Configuração dos formulários: os avulsos de {formulario} não foram todos "
                "transcritos. Nada foi alterado; é preciso uma decisão antes de seguir."
            )


def transcrever(apps, schema_editor):
    """Carrega **uma vez só**, com as tabelas vazias: se já há configuração, ela é do administrador
    (inclusive depois de desfazer e reaplicar esta migration) e nada é recolocado. Tudo numa
    transação, porque o MySQL não faz uma para a migration: se a verificação falhar, nenhuma linha
    fica gravada. Repetir é seguro (a segunda vez não faz nada)."""
    with transaction.atomic():
        _transcrever(apps)


def _transcrever(apps):
    CentroCusto = apps.get_model("catalogo", "CentroCusto")
    CentroFormulario = apps.get_model("catalogo", "CentroFormulario")
    ExcecaoMaterial = apps.get_model("catalogo", "ExcecaoMaterial")
    if CentroFormulario.objects.exists() or ExcecaoMaterial.objects.exists():
        return  # já há configuração: é do administrador, e a carga não a desfaz

    def habilitar(formulario, centros):
        for c in centros:
            CentroFormulario.objects.get_or_create(centro=c, formulario=formulario)

    for formulario in FORMULARIOS_TODOS:
        habilitar(formulario, CentroCusto.objects.all())
    habilitar("VIATURAS", CentroCusto.objects.filter(equipe_manutencao=True))
    oficina = _linha_da_oficina(CentroCusto)
    habilitar(
        "OFICINA",
        ([oficina] if oficina else []) + list(CentroCusto.objects.filter(placa__isnull=False)),
    )
    for formulario, modelo in (("OFICINA", "MaterialOficina"), ("EPIS", "MaterialEpi")):
        for avulso in apps.get_model("catalogo", modelo).objects.all():
            ExcecaoMaterial.objects.get_or_create(
                material_id=avulso.material_id,
                formulario=formulario,
                defaults={"habilitado": True},
            )
    conferir(apps)


def desfazer(apps, schema_editor):
    """Não apaga nada: depois da implantação as tabelas guardam também as escolhas do administrador,
    que a reversão não saberia distinguir das linhas transcritas, e o código antigo não as lê (os
    cadastros antigos nunca foram tocados). As tabelas somem ao desfazer a `0006`; reaplicar a
    `0007` é seguro (idempotente)."""


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0006_configuracao_formularios"),
    ]

    operations = [
        migrations.RunPython(transcrever, desfazer),
    ]
