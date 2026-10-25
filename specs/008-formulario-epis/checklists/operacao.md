# Checklist de operação: Formulário de EPIs

**Purpose**: Avaliar a qualidade dos requisitos da operação de EPIs (regras de negócio, autorização,
acesso, dados pessoais, rastreabilidade e a fronteira entre exigência normativa e decisão do SAEP) antes
das tarefas.
**Created**: 2026-10-23
**Feature**: [spec.md](../spec.md)

> Itens marcados `[x]` significam que o revisor considerou o critério de qualidade dos requisitos
> atendido, não que a implementação está pronta. O `/speckit-implement` lê o estado, mas não o muda.

## Requirement Completeness

- [ ] CHK001 Os requisitos distinguem solicitação, autorização, entrega, recebimento e baixa no SCPI, dizendo qual evento comprova cada uma? [Completeness, Spec §Contexto]
- [ ] CHK002 Está especificado quem pode decidir, o que a decisão grava (quem, quando, motivo) e que ela é definitiva? [Completeness, Spec §FR-010, §FR-012, §FR-013, §FR-021]
- [ ] CHK003 Estão especificadas todas as situações em que o pedido de EPI não pode ser atendido (aguardando e recusado) e o que o almoxarifado vê em cada uma? [Completeness, Spec §FR-022, §FR-023, §FR-025]
- [ ] CHK004 Está especificado quando cada aviso do Telegram sai e quando não sai (registro, autorização, recusa, reenvio, chat não configurado)? [Completeness, Spec §FR-026, §FR-027, §FR-028]
- [ ] CHK005 Os requisitos dizem o que o servidor vê depois de enviar e como obtém o resultado sem login? [Completeness, Spec §FR-009, §FR-031, §FR-031b]
- [ ] CHK006 Está definido o que a recusa implica para o servidor (pedido novo) e que não existe reabertura? [Completeness, Spec §FR-010, §Fora do escopo]

## Requirement Clarity

- [ ] CHK007 "Aguardando autorização" está distinto, sem ambiguidade, de "Aguardando atendimento" já existente? [Clarity, Ambiguity, Spec §FR-008, §FR-023, Plan §R2]
- [ ] CHK008 "Acesso próprio" da Segurança do Trabalho está definido pelo que pode e pelo que não pode abrir, e não só por "ver a fila"? [Clarity, Spec §FR-017, §US6]
- [ ] CHK009 A frase da tela de sucesso está definida pelo que diz e pelo que não pode sugerir ("o EPI será entregue")? [Clarity, Spec §FR-009]
- [ ] CHK010 "Motivo da recusa" tem limite, obrigatoriedade e destinatários (servidor e almoxarifado) definidos? [Clarity, Spec §FR-012, §FR-031]
- [ ] CHK011 O que a consulta pública mostra e o que ela nunca mostra estão listados? [Clarity, Spec §FR-031, §FR-031a]
- [ ] CHK012 "Mais antigo primeiro" e o conteúdo da fila (aguardando e decididos) estão definidos? [Clarity, Spec §FR-011, §Assumptions (h)]

## Requirement Consistency

- [ ] CHK013 As decisões do usuário (Clarifications) e os requisitos (FR-001 a FR-033) dizem o mesmo sobre quem autoriza, definitividade e avisos? [Consistency, Spec §Clarifications, §FR-021]
- [ ] CHK014 "Sem alteração de materiais pela Segurança do Trabalho" é coerente com "troca e acréscimo pelo almoxarifado no atendimento sem nova autorização"? [Consistency, Spec §FR-014, §FR-024]
- [ ] CHK015 O requisito de a consulta ser pública é coerente com a decisão de desenho de que o número do pedido não vira página pública (a tela de sucesso não tem URL própria), e a exceção está justificada? [Conflict, Spec §FR-031, Plan §R6]
- [ ] CHK016 A restrição do acesso (FR-017) é coerente com a permissão das páginas públicas ao usuário da Segurança do Trabalho? [Consistency, Spec §FR-017, §Assumptions]
- [ ] CHK017 Os critérios de sucesso cobrem cada requisito central (autorização antes do atendimento, acesso, avisos, consulta) sem contradizê-los? [Consistency, Spec §SC-001 a SC-008]

## Acceptance Criteria Quality

- [ ] CHK018 Cada requisito de bloqueio ("não pode ser atendido") tem critério verificável que valha também para envio forjado? [Measurability, Spec §FR-023, §SC-002, §US3-1]
- [ ] CHK019 O limite de tempo do aviso ao almoxarifado depois da autorização (1 minuto) é mensurável e depende de configuração declarada? [Measurability, Spec §SC-005]
- [ ] CHK020 "100% das tentativas" de acesso indevido (SC-004) tem o universo definido (todas as rotas da parte interna)? [Measurability, Spec §SC-004, Plan §Testes]
- [ ] CHK021 Existe critério mensurável para o tempo entre o pedido e a decisão, ou a ausência dele é intencional? [Gap, Spec §FR-016, §(f)]

## Scenario Coverage

- [ ] CHK022 Estão cobertos os fluxos primário (pedir, autorizar, atender), alternativo (recusar) e de consulta? [Coverage, Spec §US1 a US6]
- [ ] CHK023 Estão cobertas a decisão simultânea por dois usuários e a decisão repetida (duplo clique)? [Coverage, Exception Flow, Spec §FR-015, §US2-6]
- [ ] CHK024 Está coberto o que acontece quando o chat da Segurança do Trabalho não está configurado ou o envio falha? [Coverage, Exception Flow, Spec §FR-026, §Edge Cases]
- [ ] CHK025 Estão cobertos o estoque que muda entre envio, autorização e atendimento e o material que sai da escolha? [Coverage, Edge Case, Spec §Edge Cases]
- [ ] CHK026 Está coberto o pedido que fica sem decisão por ausência da Segurança do Trabalho (sem substituto, sem prazo)? [Coverage, Gap, Spec §FR-016, §FR-021, §(f)]

## Edge Case Coverage

- [ ] CHK027 Estão tratados o usuário da Segurança do Trabalho que pede em nome próprio e o que decide o próprio pedido? [Edge Case, Spec §Edge Cases, §(j)]
- [ ] CHK028 Está tratado o recebedor diferente do solicitante, dado que a NR-6 fala em fornecimento ao empregado? [Edge Case, Spec §Edge Cases, §(i)]
- [ ] CHK029 Está tratado o usuário da Segurança do Trabalho desativado depois de decidir? [Edge Case, Spec §Edge Cases]
- [ ] CHK030 Está tratado o número de pedido inexistente, de outro formulário e a varredura de números sequenciais na consulta? [Edge Case, Spec §FR-031a, Plan §R6]

## Non-Functional Requirements (acesso, dados pessoais, rastreabilidade)

- [ ] CHK031 Os requisitos de controle de acesso exigem negar por padrão rotas novas, e não só as existentes hoje? [Coverage, Spec §FR-017, Plan §R4]
- [ ] CHK032 Está definido que usuários e telas do almoxarifado existentes continuam com o mesmo acesso? [Completeness, Spec §FR-018, §FR-033]
- [ ] CHK033 Os dados pessoais tratados (nome, decisão, motivo) e o que a consulta pública pode expor estão enumerados, com o prazo de guarda registrado como pendência? [Completeness, Spec §Assumptions, §Pendências 5]
- [ ] CHK034 A rastreabilidade mínima (quem decidiu, quando, motivo, quem atendeu, quem recebeu) está definida e as lacunas (CA, tamanho, motivo de reposição) estão declaradas fora do escopo? [Traceability, Spec §FR-013, §Fora do escopo]
- [ ] CHK035 A segurança da consulta pública (CSRF, resposta neutra, limite por origem, sem cache) está especificada no plano e o requisito da spec a sustenta? [Traceability, Spec §FR-031a, Plan §R6]

## Normative vs. internal procedure

- [ ] CHK036 Cada item da NR-6 citado está classificado como exigência, boa prática, procedimento interno ou fora de escopo, com o item da norma? [Traceability, Spec §Referências normativas]
- [ ] CHK037 A spec evita declarar conformidade e lista as validações externas necessárias (regime dos servidores, suficiência do registro, relatório, descartáveis, prazo de guarda)? [Clarity, Spec §Referências normativas]
- [ ] CHK038 A ausência de exportação de relatório está explícita como decisão do usuário, ligada ao item 6.5.1.1? [Traceability, Spec §Clarifications, §Fora do escopo]
- [ ] CHK039 Está claro que a autorização da Segurança do Trabalho é procedimento do SAEP e não prova o cumprimento da seleção do EPI (6.5.2.2)? [Clarity, Spec §Referências normativas]

## Dependencies & Assumptions

- [ ] CHK040 As pré-condições da implantação estão registradas: criação do grupo e dos usuários, carga da escolha dos EPIs e o segundo chat do Telegram? [Assumption, Spec §Assumptions, Plan §R5]
- [ ] CHK041 A dependência de a Segurança do Trabalho consultar a fila (e não só o aviso) está registrada? [Dependency, Spec §SC-006]
- [ ] CHK042 O que fica fora (CA, tamanho, motivo, relatório, assinatura eletrônica, reversão, outras aprovações) está explícito? [Scope, Spec §Fora do escopo]

## Notes

- Avaliação do autor (2026-10-23), a pedido do fluxo ("corrija as lacunas na spec antes de seguir"). As
  lacunas abaixo foram corrigidas na spec; os itens ficam para o revisor marcar:
  - CHK009: FR-009 passou de "não há entrega garantida" para uma frase testável (a entrega só acontece
    depois da autorização, no atendimento; não sugerir entrega).
  - CHK010: FR-012 ganhou o aviso de que o motivo da recusa é visto pelo servidor e pelo almoxarifado.
  - CHK016 e CHK033: Assumptions passaram a dizer que as páginas públicas continuam abertas ao usuário
    da Segurança do Trabalho e a listar os dados pessoais tratados.
  - CHK027, CHK028 e CHK029: três casos de borda novos (autoautorização, recebedor diferente,
    motivo com dado sensível) e as pendências (i) e (j) em "A esclarecer".
- Lacunas que **não** foram preenchidas por suposição, e seguem abertas para o usuário: CHK021 (não há
  prazo-alvo para decidir), CHK027 e CHK028 (política do SAEP), além das pendências normativas.
- CHK015: a consulta pública contraria a decisão de desenho de a tela de sucesso não ter URL própria;
  a exceção foi pedida pelo usuário e é limitada (Plan §R6). O endurecimento com o nome completo é
  proposta ao usuário, não requisito.

## Verificação da implementação (2026-10-23)

Anotação do autor, sem marcar itens (a revisão dos requisitos é do revisor):

- Portões: `ruff check` e `ruff format --check` limpos, `makemigrations --check` sem pendência,
  `check --deploy --fail-level WARNING` sem avisos e `pytest` com 1696 passando e 1 pulado (o pulado é
  de antes: flags do Windows). Linha de base antes da feature: 1534 passando e 1 pulado.
- Roteiro manual (quickstart) num banco descartável local, no navegador embutido, com os dados do
  cenário de teste: consulta pública, login do usuário do grupo caindo na fila, fila em cartões no
  celular, detalhe só de leitura, recusa sem motivo negada, recusa com motivo gravada, tentativa de
  abrir a saída avulsa e o admin redirecionada à fila, painel do almoxarifado com "Aguardando
  autorização" e "Recusado" e atalho "Atender" em 0, detalhe do aguardando sem o formulário de
  atendimento. **Não conferido à mão**: o envio do formulário de EPIs pelo navegador (os campos usam
  controles customizados que a automação não digitou; o envio tem teste automatizado), o Telegram real
  (os testes simulam o envio) e o Pester (`pwsh` não está instalado nesta máquina).
- Achados da verificação, já corrigidos: o `select_related("autorizacao")` que faltava no painel (o
  teste de consultas limitadas o pegou) e a fila de autorização que não virava cartões no celular.
