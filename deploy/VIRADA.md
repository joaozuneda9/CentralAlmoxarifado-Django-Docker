# Migração e virada: do Apps Script para o Django

> Registro do roteiro histórico do Apps Script, já executado. O sistema já tem dados reais.
> O comando `importar_planilhas` e os módulos `conversao` e `migracao` citados aqui foram
> removidos depois da virada (seção 7); o código fica na tag `v1.0.1`.
> Para a nova produção no mesmo Docker Desktop, seguir [AMBIENTES.md](AMBIENTES.md).
> Não repetir importações destrutivas nem os comandos de atualização deste roteiro
> na instalação em uso. O atualizador legado está bloqueado.

Roteiro para o João (desenvolvedor) e o André (servidor). Cada passo diz quem faz. Marque as
caixas à medida que terminar; a ordem importa. A spec (seção 8) explica o porquê de cada etapa.

Os comandos são para o terminal do servidor (no Windows Server, o do Ubuntu no WSL2), na pasta
do sistema (`cd /srv/almoxarifado`), e rodam dentro do container `web` (`docker compose exec
web ...`). Os endereços usam `servidor` no lugar do nome real, como no `INSTALACAO.md`:

| O quê | Endereço |
|---|---|
| Formulários dos funcionários | `https://servidor/almoxarifado/` |
| Área do almoxarifado (login) | `https://servidor/almoxarifado/painel/` |
| Cadastros (admin) | `https://servidor/almoxarifado/admin/` |

Até a virada o Apps Script continua sendo o sistema em uso, e o Django roda ao lado com o
lançamento real **bloqueado** (`LANCAMENTO_REAL=0`): o comando, a página Automações e o
painel só simulam. Isso evita lançar duas vezes no SCPI as mesmas saídas pendentes.

## 1. Instalação (André)

- [ ] Instalar o sistema no servidor seguindo `deploy/INSTALACAO.md`, inclusive a conferência da
      seção 10, **com `LANCAMENTO_REAL=0`** no `.env`.
- [ ] Confirmar que o painel mostra o aviso "Lançamento real bloqueado até a virada" e que, em
      Automações › Lançamento no SCPI, só a simulação está disponível.
- [ ] Deixar `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` **vazios** no `.env` até a virada: um pedido de
      teste feito no Django avisaria o grupo de verdade. Eles são preenchidos no passo 6.

## 2. Carga inicial do catálogo (João)

O cadastro de materiais precisa existir antes das planilhas, porque os itens de limpeza apontam
para ele. Os robôs que abrem o SCPI (cadastro, estoque, saídas) entram com o `SAEP_USER` e a
`SAEP_PASS` do `.env` do servidor e usam o perfil do navegador do volume `perfil-navegador`; o
Chromium vem na imagem e o `.env` é o da `INSTALACAO.md` (seção 4). O primeiro acesso do
servidor ao SCPI é aqui: se o login falhar, veja o `dados/logs/almoxarifado.log` antes de repetir.

- [ ] Baixar do SCPI o CSV do **cadastro completo** de materiais.
- [ ] Em `https://servidor/almoxarifado/painel/automacoes/`, aba **Cadastro**: origem "CSV
      enviado", modo "recarga completa", enviar o arquivo. (O cadastro inteiro é carregado uma
      vez; depois o robô diário só traz os novos.) Conferir o resultado na aba Visão geral.
- [ ] Carregar o estoque:

      ```bash
      cd /srv/almoxarifado
      docker compose exec web python manage.py importar_estoque
      ```

- [ ] Carregar as saídas do SCPI desde **01/01/2026** (os dados anteriores não são confiáveis
      e nunca entram na curva ABC nem na reposição):

      ```bash
      docker compose exec web python manage.py importar_saidas_scpi --desde 01/01/2026
      ```

- [ ] Carregar os pares de/para. **Não desative nem apague a planilha MAPEAMENTO DE/PARA
      CONSOLIDADO** até esta carga ser conferida: ela é a única fonte dos pares. Exportar a
      planilha ("Arquivo › Fazer download › Microsoft Excel (.xlsx)"), salvar como
      `dados/importacao/mapeamento.xlsx` na pasta do sistema (no container,
      `/dados/importacao/mapeamento.xlsx`) e simular:

      ```bash
      docker compose exec web python manage.py importar_depara --arquivo /dados/importacao/mapeamento.xlsx --dry-run
      ```

      Ler os recusados (com aba, linha e motivo) e corrigir na planilha o que for erro. Depois,
      sem `--dry-run`. A carga substitui todos os pares e é recusada se algum par já foi criado
      ou alterado no admin: depois dela, os pares são mantidos em Cadastros › Pares de/para.
- [ ] Em Painel › Curva ABC, conferir a curva por frequência contra a aba `ABC_FREQ_CONSOL` da
      planilha (ordem e classe em pelo menos 99% dos materiais; `specs/001-depara-curva-abc/quickstart.md`,
      seção 4) e a reconciliação dos totais.

- [ ] Em Automações › Visão geral, nenhum alerta de erro ou de dado velho.

## 3. Primeira importação das planilhas (João)

- [ ] Na planilha do sistema (Google Sheets): "Arquivo › Fazer download › Microsoft Excel
      (.xlsx)". Salvar como `dados/importacao/planilha.xlsx` na pasta do sistema (fora do git;
      no container, `/dados/importacao/planilha.xlsx`). A planilha tem dados dos pedidos:
      apague o arquivo quando terminar (passo 6).
- [ ] Simular a importação:

      ```bash
      cd /srv/almoxarifado
      docker compose exec web python manage.py importar_planilhas --arquivo /dados/importacao/planilha.xlsx --dry-run
      ```

      A simulação é um ensaio fiel: converte a planilha, lista os problemas dela e grava tudo
      dentro de uma transação que é desfeita no fim (nada fica gravado). As travas e as
      restrições do banco valem como na importação de verdade: ela recusa se `LANCAMENTO_REAL`
      estiver ligado, se o banco tiver pedido que não está na planilha, se tiver atendimento
      feito no Django ou se não houver nenhum material cadastrado.
- [ ] Na primeira simulação de verdade, **comparar os totais do resumo com o número de linhas de
      cada aba no Google Sheets** (pedidos, itens, saídas, centros de custo e as listas). Aviso de
      "item sem pedido", "linha sem ID" ou "saída sem atendimento ignorada" explica a diferença;
      diferença sem aviso é motivo para parar e investigar.
- [ ] Corrigir **na planilha** cada erro listado e repetir a simulação até não haver erro. Em
      geral a correção é "Concluir transferência" no Apps Script ou marcar a saída como NÃO
      LANÇAR. Texto que passa do tamanho do campo (observações, nomes) é erro e deve ser
      encurtado na planilha. Os avisos são lidos e aceitos (o que só se perde como histórico).
- [ ] Exportar de novo, se corrigiu algo, e importar de verdade:

      ```bash
      docker compose exec web python manage.py importar_planilhas --arquivo /dados/importacao/planilha.xlsx
      ```

      O resumo mostra os totais e o "último número". A importação grava numa transação: ou entra
      tudo ou nada.

## 4. Contas do painel (João)

A aba "Almoxarifado" do sistema antigo (e-mails de quem atende) **não é importada**. Quem usa o
painel precisa de conta própria, com a matrícula como usuário.

- [ ] Usar a aba "Almoxarifado" do Apps Script como lista de quem precisa de conta.
- [ ] Em `https://servidor/almoxarifado/admin/`, criar um usuário para cada um, com a matrícula
      e uma senha. Qualquer usuário ativo entra no painel; só quem também mexe nos cadastros
      (centros de custo, opções, itens de limpeza) precisa de "Membro da equipe" e das
      permissões correspondentes.
- [ ] Cada pessoa testa o login em `https://servidor/almoxarifado/painel/entrar/`.

## 5. Período em paralelo (João e quem atende; pelo menos uma semana de lançamentos)

- [ ] O Apps Script continua sendo o sistema em uso. **Nenhum pedido é feito direto no Django,
      nem atendimento, nem saída avulsa.** Se for feito, a reimportação recusa até o registro
      ser desfeito. O admin não apaga pedidos (é só leitura); use o shell, na pasta do sistema:

      Pedido de teste feito no Django (troque a lista pelos números que a recusa mostrou):

      ```bash
      cd /srv/almoxarifado
      docker compose exec web python manage.py shell -c "from pedidos.models import Pedido; Pedido.objects.filter(numero__in=['P-000001']).delete()"
      ```

      Atendimento feito no Django sobre um pedido que veio da planilha (apaga os materiais
      acrescentados pelo almoxarifado e o atendimento, as linhas de saída vão junto, e zera a
      quantidade entregue dos itens):

      ```bash
      docker compose exec web python manage.py shell -c "from pedidos.models import Atendimento, ItemPedido; n=['P-000120']; ItemPedido.objects.filter(pedido__numero__in=n, origem='ALMOXARIFADO').delete(); Atendimento.objects.filter(pedido__numero__in=n).delete(); ItemPedido.objects.filter(pedido__numero__in=n).update(qtd_entregue=None)"
      ```

      (a importação seguinte repõe tudo a partir da planilha; se a linha de saída do atendimento
      desfeito já tinha sido lançada no SCPI pelo Django, não era período em paralelo: pare e
      confira com o João.)
- [ ] A cada conferência, exportar a planilha de novo e rodar `importar_planilhas` (passo 3).
      **A importação substitui tudo** o que veio da planilha: pedidos, centros de custo, opções e
      itens de limpeza.
- [ ] No Django, conferir contra o painel antigo os números, a situação e a situação no SCPI de
      cada pedido.
- [ ] Usar "Simular" em Automações › Lançamento no SCPI e comparar os lotes simulados com o que o robô antigo
      lançou.
- [ ] O agendador está rodando (estoque, catálogo, backup) e `dados/logs/agendador.log` não tem
      erros. O backup diário gera arquivos em `dados/backups`.

## 6. Virada (João e André, fora do expediente)

A ordem abaixo **difere de propósito da spec (seção 8, passos 2 a 4)**: o Apps Script é congelado
antes de esvaziar as pendências do robô antigo e de exportar a planilha, porque, enquanto os
formulários antigos estiverem no ar, entra pedido novo depois da exportação (a saída se perderia)
ou o robô antigo lança uma saída que o Django lançaria de novo.

- [ ] **João:** congelar o Apps Script. Trocar o `doGet` (`AS:apps-script/WebApp.gs`) por uma
      página de manutenção; os formulários e o painel antigos saem do ar e nada novo entra na
      planilha:

      ```js
      function doGet() {
        return HtmlService.createHtmlOutput(
          '<p>Sistema em manutenção. Volte em instantes.</p>'
        ).setTitle('Central Almoxarifado');
      }
      ```

      Publicar uma nova versão da implantação e abrir o endereço antigo para conferir.
- [ ] **João:** esvaziar as pendências do robô antigo: rodar o `lancar_saidas.py` do Apps Script
      até não restar linha pendente, e conferir no SCPI cada "VERIFICAR NO SCPI" e "EM
      LANÇAMENTO" (resolvê-las na planilha).
- [ ] **João:** desativar de vez o `lancar_saidas.py` antigo, antes de liberar o lançamento real
      no Django: remover ou desabilitar qualquer tarefa agendada que o rode, avisar quem o rodava
      à mão e conferir que ninguém mais o roda. As duas versões lançariam as mesmas saídas no
      SCPI, e arquivar o repositório (último passo) não impede um script que já está numa
      máquina.
- [ ] **João:** importação final: exportar a planilha, `importar_planilhas --dry-run` e importar
      (passo 3). Anotar o "último número" do resumo e conferir que é o último Nº da planilha
      congelada.
- [ ] **João:** trocar o `doGet` por uma página que aponta para o endereço novo:

      ```js
      function doGet() {
        return HtmlService.createHtmlOutput(
          '<p>O Central Almoxarifado mudou de endereço: <a href="https://ENDERECO-NOVO/" target="_top">abrir</a>.</p>'
        ).setTitle('Central Almoxarifado');
      }
      ```

- [ ] **André:** liberar o lançamento real: `LANCAMENTO_REAL=1` no `.env`, preencher
      `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` (que estavam vazios desde o passo 1) e recriar os
      containers (o `restart` não relê o `.env`):

      ```bash
      cd /srv/almoxarifado
      nano .env
      docker compose up -d
      ```

- [ ] **João:** primeiro lançamento real, em Automações › Lançamento no SCPI, com "Só as
      primeiras 1 requisições" e o botão "Lançar no SCPI". Conferir a requisição no SCPI. Só depois liberar o
      lançamento sem limite.
- [ ] Os funcionários passam a usar `https://servidor/almoxarifado/` (formulários) e a equipe,
      `https://servidor/almoxarifado/painel/`.
- [ ] **João:** arquivar o repositório do Apps Script: `gh repo archive <dono>/CentralAlmoxarifado`.
- [ ] **João:** por último, apagar os `.xlsx` exportados (`dados/importacao/`):
      só depois de arquivar o repositório e de conferir o primeiro lançamento, porque até lá a
      planilha é o único retrato do que veio do sistema antigo.

## 7. Depois da virada

- `importar_planilhas` e seus módulos (`conversao`, `migracao`) foram removidos do app
  `implantacao`; o `planilha` ficou, reduzido ao leitor de `.xlsx` que o `importar_depara` usa.
  O backup e `robos_em_andamento` ficam.
- Mudança de modelo passa a ter **migration nova**, nunca regenerada (o banco agora tem dados
  reais). Atualizações pelo `deploy/atualizar.sh` (`INSTALACAO.md`, seção 9).
- O backup diário segue valendo; copie a pasta de backup para outra máquina de vez em quando.
