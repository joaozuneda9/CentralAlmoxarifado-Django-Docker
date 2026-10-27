# Instalação na máquina de produção

O ambiente confirmado em 19/10/2026 é **Windows 10 Pro 64 bits**, WSL 2.5.9,
Docker Desktop 4.36.0, Engine 27.3.1 e Compose 2.30.3. Há produção em uso e
outros containers (`gis-stack`) no mesmo Docker. Não reiniciar Windows, WSL ou
Docker, não reinstalar componentes e não executar limpeza de recursos.

A produção fica em `C:\docker\producao`. Hoje roda pelo `compose.yaml` legado, com
projeto `almoxarifado_prod`; o projeto `almoxarifado-prod` é o que o `atualizar.ps1` espera
(ver a nota de situação em [AMBIENTES.md](AMBIENTES.md)).
A instalação do Desktop continua atendendo os usuários até a virada. Ter outra
pasta não basta: o Compose legado fixa o nome do projeto e a imagem.

Leia [AMBIENTES.md](AMBIENTES.md) para a preparação, migração e atualização e
[FLUXO_GIT.md](FLUXO_GIT.md) para branches, PRs, versões e publicação de imagens.
O `deploy/atualizar.sh` antigo agora recusa execução; não atualize esta máquina
seguindo os passos antigos de `git pull` e `docker compose up` sem alvo explícito.

O acesso atual é HTTP em `45.172.240.231:8010`, provavelmente encaminhado pelo
MikroTik ao Windows `192.168.0.241`. A regra exata ainda depende de confirmação
com o André. **Não há Apache ou HTTPS confirmado.** A nova configuração publica
somente em loopback e requer proxy HTTPS para uso real. Não alterar a regra do
MikroTik para uma porta loopback: ela não fica acessível diretamente pela rede.

O guia `VIRADA.md` descreve a migração histórica do Apps Script, já realizada;
não é o roteiro para copiar os dados reais entre estas duas instalações Docker.
A recuperação automática após reiniciar a máquina também não foi validada e
não deve ser testada por reinicialização nesta operação.
