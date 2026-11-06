#!/usr/bin/env bash
# Resolve as duas configuracoes sem falar com o daemon e sem ler .env real.
set -euo pipefail
raiz=$(cd "$(dirname "$0")/../.." && pwd)
temporario=$(mktemp -d)
trap 'rm -rf "$temporario"' EXIT
cp "$raiz"/compose.{ambientes,desenvolvimento,producao}.yaml "$temporario/"
cat > "$temporario/.env" <<'FIM'
SECRET_KEY=descartavel
DB_USER=almox
DB_PASSWORD=teste
SAEP_USER=nao-pode-vazar
SAEP_PASS=nao-pode-vazar
TELEGRAM_TOKEN=nao-pode-vazar
TELEGRAM_CHAT_ID=nao-pode-vazar
LANCAMENTO_REAL=1
# Valor legado propositalmente inseguro: nao pode selecionar o bind dos novos ambientes.
PORTA_PUBLICADA=0.0.0.0:8010
FIM
echo 'MARIADB_ROOT_PASSWORD=teste' > "$temporario/.env.banco"
for ambiente in desenvolvimento producao; do
  projeto="teste-$ambiente"
  [ "$ambiente" = producao ] && projeto=almoxarifado_prod
  PROJETO_COMPOSE="$projeto" AMBIENTE_DEPLOY="$ambiente" \
    REVISAO_APP=abc123 IMAGEM_APP="teste-$ambiente:abc123" \
    docker compose --project-directory "$temporario" --env-file "$temporario/.env" \
    -f "$temporario/compose.ambientes.yaml" -f "$temporario/compose.$ambiente.yaml" \
    --profile '*' config --format json > "$temporario/$ambiente.json"
done
PROJETO_COMPOSE=teste-porta AMBIENTE_DEPLOY=desenvolvimento \
  REVISAO_APP=abc123 IMAGEM_APP=teste-porta:abc123 PORTA_WEB=18011 \
  docker compose --project-directory "$temporario" --env-file "$temporario/.env" \
  -f "$temporario/compose.ambientes.yaml" -f "$temporario/compose.desenvolvimento.yaml" \
  --profile '*' config --format json > "$temporario/porta.json"
python3 - "$temporario" <<'PY'
import json
import sys
from pathlib import Path

pasta = Path(sys.argv[1])
dev = json.loads((pasta / 'desenvolvimento.json').read_text())
prod = json.loads((pasta / 'producao.json').read_text())
assert prod['name'] != dev['name']
assert prod['volumes']['banco-dados']['name'] != dev['volumes']['banco-dados']['name']
assert prod['volumes']['perfil-navegador']['name'] != dev['volumes']['perfil-navegador']['name']
for nome in ('web', 'agendador'):
    d, p = dev['services'][nome], prod['services'][nome]
    assert d['image'] != p['image']
    assert 'build' not in p
    assert d['environment']['LANCAMENTO_REAL'] == '0'
    for chave in ('SAEP_USER', 'SAEP_PASS', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID'):
        assert d['environment'][chave] == ''
    assert d['environment']['DB_HOST'] == p['environment']['DB_HOST'] == 'banco'
    assert 'MARIADB_ROOT_PASSWORD' not in d['environment']
assert 'agendamento' in prod['services']['agendador']['profiles']
# Producao real: HTTP direto na rede, sem confiar em proxy (deploy/AMBIENTES.md).
assert prod['name'] == 'almoxarifado_prod'
assert prod['services']['web']['container_name'] == 'almoxarifado_prod'
assert len(prod['services']['web']['ports']) == 1
assert prod['services']['web']['ports'][0]['host_ip'] == '0.0.0.0'
assert prod['services']['web']['ports'][0]['published'] == '8012'
assert not any('trusted-proxy' in arg for arg in prod['services']['web']['command'])
# Desenvolvimento segue so em loopback e com a base intacta.
assert len(dev['services']['web']['ports']) == 1
assert dev['services']['web']['ports'][0]['host_ip'] == '127.0.0.1'
assert '--trusted-proxy=*' in dev['services']['web']['command']
porta = json.loads((pasta / 'porta.json').read_text())['services']['web']['ports'][0]
assert porta['host_ip'] == '127.0.0.1' and porta['published'] == '18011'
assert not prod['services']['banco'].get('ports')
print('PASS: projetos, imagens, volumes, credenciais e portas isolados no Compose resolvido.')
PY
for invalida in '0.0.0.0:18011' '[::]:18011'; do
  if PROJETO_COMPOSE=teste-porta AMBIENTE_DEPLOY=desenvolvimento \
    REVISAO_APP=abc123 IMAGEM_APP=teste-porta:abc123 PORTA_WEB="$invalida" \
    docker compose --project-directory "$temporario" --env-file "$temporario/.env" \
    -f "$temporario/compose.ambientes.yaml" -f "$temporario/compose.desenvolvimento.yaml" \
    config --quiet > "$temporario/invalida.log" 2>&1; then
    echo 'FAIL: PORTA_WEB aceitou endereco em vez de numero de porta.' >&2
    exit 1
  fi
done
