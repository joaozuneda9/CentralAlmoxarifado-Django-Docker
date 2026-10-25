"""O admin dos centros de custo na spec 009: `ativo` no lugar da marca de equipe de manutenção."""

import pytest
from django.contrib import admin
from django.urls import reverse

from catalogo.models import CentroCusto, CentroFormulario, MaterialEpi, MaterialOficina
from tests.config_cenario import criar_centro

pytestmark = pytest.mark.django_db

LISTA = reverse("admin:catalogo_centrocusto_changelist")


def test_a_lista_mostra_e_filtra_por_ativo_e_nao_tem_mais_a_marca_de_equipe(admin_client):
    criar_centro("SETOR PARADO", "88", ativo=False)
    criar_centro("SETOR VIVO", "89")
    html = admin_client.get(LISTA).text
    assert "Ativo" in html and "ativo__exact" in html
    assert "equipe_manutencao" not in html and "Equipe de manutenção" not in html
    inativos = admin_client.get(LISTA, {"ativo__exact": "0"}).text
    assert "SETOR PARADO" in inativos and "SETOR VIVO" not in inativos


def test_o_formulario_do_centro_nao_tem_a_marca_antiga_e_tem_ativo(admin_client):
    html = admin_client.get(reverse("admin:catalogo_centrocusto_add")).text
    assert 'name="ativo"' in html and 'name="equipe_manutencao"' not in html


def test_criar_centro_pelo_admin_o_deixa_ativo_e_sem_formulario(admin_client):
    r = admin_client.post(
        reverse("admin:catalogo_centrocusto_add"),
        {"descricao": "SETOR DO ADMIN", "codigo": "99", "placa": "", "ativo": "on"},
    )
    assert r.status_code == 302
    centro = CentroCusto.objects.get(descricao="SETOR DO ADMIN")
    assert centro.ativo is True and not CentroFormulario.objects.filter(centro=centro).exists()


def test_inativar_pela_lista_do_admin(admin_client):
    centro = criar_centro("SETOR VIVO", "89")
    r = admin_client.post(
        LISTA,
        {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(centro.pk),
            "form-0-ativo": "",  # desmarcado
            "_save": "Salvar",
        },
    )
    assert r.status_code == 302
    assert CentroCusto.objects.get(pk=centro.pk).ativo is False


def test_os_avulsos_antigos_e_a_marca_nao_estao_mais_no_admin():
    assert MaterialOficina not in admin.site._registry and MaterialEpi not in admin.site._registry
