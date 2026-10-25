# Checklist de operação: Formulário da oficina mecânica

**Purpose**: Avaliar a qualidade dos requisitos da operação da oficina (cenários excepcionais,
destinos, escolha de grupos e materiais, consistência com os formulários públicos existentes) antes
das tarefas.
**Created**: 2026-10-22
**Feature**: [spec.md](../spec.md)

> Itens marcados `[x]` significam que o revisor considerou o critério de qualidade dos requisitos
> atendido, não que a implementação está pronta. O `/speckit-implement` lê o estado, mas não o muda.

## Requirement Completeness

- [ ] CHK001 Os requisitos definem todas as origens possíveis de material do formulário (grupos e materiais avulsos) e como se combinam? [Completeness, Spec §FR-003, §FR-012a]
- [ ] CHK002 Está especificado o que acontece com um material avulso oculto no SCPI (não aparece e é avisado)? [Completeness, Spec §FR-013]
- [ ] CHK003 Está especificado o comportamento da saúde do catálogo quando falta o centro OFICINA MECÂNICA, mas há viaturas? [Gap, Spec §Edge Cases]
- [ ] CHK004 Os requisitos dizem onde o destino do pedido aparece para o almoxarifado (detalhe, recibo, painel, Telegram)? [Completeness, Spec §FR-008]

## Requirement Clarity

- [ ] CHK005 O critério de comparação entre o nome do grupo escolhido e o grupo do cadastro (acentos, maiúsculas, espaços) está definido? [Clarity, Spec §FR-012]
- [ ] CHK006 "Viatura" está definida sem ambiguidade (centro de custo com placa, inclusive bombas e equipamentos)? [Clarity, Spec §Contexto, §Key Entities]
- [ ] CHK007 A forma como a viatura é oferecida e reconhecida (descrição e placa, placa digitada) está definida? [Clarity, Spec §FR-006]
- [ ] CHK008 Como o centro OFICINA MECÂNICA é identificado no cadastro está explícito? [Clarity, Spec §Assumptions]

## Requirement Consistency

- [ ] CHK009 A regra de quantidade e de estoque é a mesma dos outros formulários públicos, sem exceção da oficina? [Consistency, Spec §FR-004, §Clarifications]
- [ ] CHK010 Os requisitos de destino deste formulário são consistentes com a regra "placa → centro" do atendimento? [Consistency, Spec §FR-009]
- [ ] CHK011 Os requisitos garantem que a escolha da oficina não altera o catálogo AB, a lista de limpeza e a lista das viaturas? [Consistency, Spec §FR-014, §Edge Cases]
- [ ] CHK012 A terminologia "escolha da oficina", "grupos da oficina" e "materiais avulsos" é usada da mesma forma em todo o documento? [Consistency]

## Acceptance Criteria Quality

- [ ] CHK013 Cada história tem um teste independente verificável sem a operação real? [Measurability, Spec §User Stories]
- [ ] CHK014 SC-002 é verificável apesar do corte de 50 resultados da busca? [Measurability, Spec §SC-002]
- [ ] CHK015 SC-001 deixa claro que depende de medição no uso real? [Measurability, Spec §SC-001]

## Scenario Coverage

- [ ] CHK016 Está coberto o caso de o material sair da escolha entre abrir o formulário e enviar? [Coverage, Gap]
- [ ] CHK017 Está coberto o caso de a viatura ser descadastrada antes e depois do envio? [Coverage, Spec §Edge Cases]
- [ ] CHK018 Estão cobertos reenvio, envio rápido, campo isca e limites por IP e por nome? [Coverage, Spec §Edge Cases]
- [ ] CHK019 Está coberto o pedido com destino OFICINA MECÂNICA (sem viatura) até o atendimento? [Coverage, Spec §US2]

## Edge Case Coverage

- [ ] CHK020 Estão definidos os casos de escolha vazia, grupo inexistente e saldo nunca importado? [Edge Case, Spec §FR-005, §FR-013]
- [ ] CHK021 Está definido o material avulso que também pertence a um grupo da oficina (aparece uma vez, retirada do avulso não o tira)? [Edge Case, Spec §FR-012a]

## Dependencies & Assumptions

- [ ] CHK022 A dependência da configuração inicial pelo almoxarifado (grupos e avulsos) está registrada como pré-condição da implantação? [Assumption, Spec §Assumptions]
- [ ] CHK023 O que fica fora (ordem de serviço, número de OS, cadastro de viaturas, ordem própria) está explícito? [Scope, Spec §Fora do escopo]

## Notes

- Avaliação do autor (2026-10-22), a pedido do fluxo ("corrija lacunas antes de prosseguir"): CHK003
  e CHK016 apontaram lacunas, corrigidas na spec (FR-013 com o aviso de centro OFICINA MECÂNICA
  ausente; caso de borda do material retirado da escolha antes do envio). Os demais itens ficam para
  o revisor marcar.
