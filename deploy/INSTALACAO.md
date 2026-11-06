# Instalação na máquina de produção

O ambiente confirmado em 19/10/2026 é **Windows 10 Pro 64 bits**, WSL 2.5.9,
Docker Desktop 4.36.0, Engine 27.3.1 e Compose 2.30.3. Há produção em uso e
outros containers (`gis-stack`) no mesmo Docker. Não reiniciar Windows, WSL ou
Docker, não reinstalar componentes e não executar limpeza de recursos.

A produção está em `C:\docker\producao`, projeto `almoxarifado_prod` (virada de
23/10/2026); a instalação do Desktop virou o desenvolvimento. A pasta
`C:\docker\almoxarifado-prod` foi uma preparação abandonada e não é produção.
O nome do projeto escolhe os volumes (o banco): não rode o Compose de produção
a partir de outra pasta. A produção ainda roda do `compose.yaml` editado à mão,
sem marcador, e o `atualizar.ps1` recusa a pasta nesse estado. Na passagem
única de [AMBIENTES.md](AMBIENTES.md), depois de restaurar o `compose.yaml`,
trocar para a tag nova e criar o marcador, o `atualizar.ps1` já é usado para
aplicar a versão; daí em diante, é ele que faz as atualizações descritas lá.

Leia [AMBIENTES.md](AMBIENTES.md) para a preparação, migração e atualização e
[FLUXO_GIT.md](FLUXO_GIT.md) para branches, PRs, versões e publicação de imagens.
O `deploy/atualizar.sh` antigo agora recusa execução; não atualize esta máquina
seguindo os passos antigos de `git pull` e `docker compose up` sem alvo explícito.

O acesso é **HTTP direto, sem Apache, proxy nem HTTPS**: o waitress da produção
publica na porta `8012` de todas as interfaces do Windows `192.168.0.241`, e o
acesso externo chega por encaminhamento do MikroTik (a regra exata, endereço
público e porta, é conferida com o André; antes da virada era
`45.172.240.231:8010`). Por estar aberto na rede, o waitress não confia em
cabeçalhos de proxy e o `.env` tem `USAR_HTTPS=0` e `PROXY_HTTPS=0`; detalhes e o
caminho para um proxy HTTPS futuro em [AMBIENTES.md](AMBIENTES.md). O
desenvolvimento publica só em loopback (`127.0.0.1:8011`) e não deve entrar na
regra do MikroTik.

O guia `VIRADA.md` descreve a migração histórica do Apps Script, já realizada;
não é o roteiro para copiar os dados reais entre estas duas instalações Docker.
A recuperação automática após reiniciar a máquina também não foi validada e
não deve ser testada por reinicialização nesta operação.
