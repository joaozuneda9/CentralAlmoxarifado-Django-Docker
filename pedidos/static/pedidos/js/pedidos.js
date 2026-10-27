/*
 * Comportamentos dos formulários de pedido. Carregado no <head> com defer.
 */
(function () {
  "use strict";

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    var alvo = e.target;
    // Enter na busca não envia o pedido.
    if (alvo.matches && alvo.matches("[data-busca]")) {
      e.preventDefault();
      return;
    }
    // Enter na quantidade do pedido confere a alteração, sem enviar o pedido inteiro.
    if (alvo.matches && alvo.matches("[data-qtd-carrinho]")) {
      e.preventDefault();
      mandarAlteracao(alvo);
      return;
    }
    // Enter numa quantidade aciona o "Adicionar" da mesma linha (o único botão com hx-post;
    // os outros são o − e o +).
    if (alvo.matches && alvo.matches(".campo-qtd")) {
      e.preventDefault();
      var linha = alvo.closest("li");
      var botao = linha && linha.querySelector("[hx-post]");
      if (botao) botao.click();
    }
  });

  // Esc na quantidade aberta (adicionar ou alterar em dois passos) só a fecha; o painel de
  // resultados e a gaveta do pedido ficam abertos. Na linha do pedido, o botão que a abre (a linha
  // toda) fica fora da ação: o Esc nele também a fecha.
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !e.target.closest) return;
    var acao = e.target.closest("[data-adicionar].aberto");
    var alterar = e.target.closest("[data-alterar].aberto");
    if (!alterar && e.target.matches("[data-alterar-abrir]")) alterar = acaoDeAlterar(e.target);
    if (alterar && !alterar.classList.contains("aberto")) alterar = null;
    if (!acao && !alterar) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (acao) fecharQuantidade(acao, true);
    else cancelarAlteracao(alterar);
  });

  // Quantidade de uma linha do pedido. Nos formulários públicos, ela só vai ao servidor no
  // "Confirmar" (`hx-trigger="confirmar-quantidade"`): "Alterar" abre o − / +, e o ✕ ou o Esc voltam
  // ao valor anterior. Na saída avulsa, cada mudança vai direto ("change").
  function mandarAlteracao(campo) {
    var publico = campo.closest("[data-alterar]");
    var evento = new Event(publico ? "confirmar-quantidade" : "change", { bubbles: true });
    campo.dispatchEvent(evento);
    return evento;
  }

  // A linha do pedido: o botão que a abre (a linha toda, transparente) e a ação (`[data-alterar]`, com a
  // quantidade, o Confirmar e o Remover) são irmãos dentro do <li>.
  function botaoDeAlterar(linha) {
    var item = linha && linha.closest("li");
    return item && item.querySelector("[data-alterar-abrir]");
  }
  function acaoDeAlterar(botao) {
    var item = botao && botao.closest("li");
    return item && item.querySelector("[data-alterar]");
  }

  function fecharAlteracao(linha, devolverFoco) {
    if (!linha || !linha.classList.contains("aberto")) return;
    linha.classList.remove("aberto");
    var abrir = botaoDeAlterar(linha);
    if (!abrir) return;
    abrir.setAttribute("aria-expanded", "false");
    if (devolverFoco) abrir.focus();
  }

  function cancelarAlteracao(linha, devolverFoco) {
    var campo = linha && linha.querySelector("[data-qtd-carrinho]");
    if (campo) campo.value = campo.defaultValue;
    fecharAlteracao(linha, devolverFoco !== false);
  }

  // Outro hx-post (remover, adicionar) manda o formulário inteiro: a quantidade aberta e não
  // confirmada volta à que estava antes, senão iria junto como se tivesse sido confirmada. Na
  // captura, antes de o HTMX juntar os campos.
  document.addEventListener(
    "click",
    function (e) {
      var botao = e.target.closest && e.target.closest("[hx-post]");
      // O <form hx-post> também casa (é ancestral de todo clique): só vale o botão que dispara outro envio.
      if (!botao || botao.matches("form")) return;
      document.querySelectorAll("[data-alterar].aberto").forEach(function (linha) {
        cancelarAlteracao(linha, false);
      });
    },
    true
  );

  function abrirAlteracao(linha) {
    document.querySelectorAll("[data-alterar].aberto").forEach(function (outra) {
      if (outra !== linha) cancelarAlteracao(outra);
    });
    linha.classList.add("aberto");
    botaoDeAlterar(linha).setAttribute("aria-expanded", "true");
    var campo = linha.querySelector("[data-qtd-carrinho]");
    campo.focus();
    var fim = campo.value.length; // cursor no fim do número, sem selecioná-lo
    campo.setSelectionRange(fim, fim);
  }

  document.addEventListener("click", function (e) {
    var alvo = e.target;
    if (!alvo || !alvo.closest) return;
    var abrir = alvo.closest("[data-alterar-abrir]");
    if (abrir) {
      var linha = acaoDeAlterar(abrir);
      // Tocar de novo na linha aberta a fecha, voltando à quantidade de antes (como o ✕).
      return linha.classList.contains("aberto") ? cancelarAlteracao(linha) : abrirAlteracao(linha);
    }
    var cancelar = alvo.closest("[data-alterar-cancelar]");
    if (cancelar) return cancelarAlteracao(cancelar.closest("[data-alterar]"));
    var confirmar = alvo.closest("[data-alterar-confirmar]");
    if (confirmar) {
      var campo = confirmar.closest("[data-alterar]").querySelector("[data-qtd-carrinho]");
      if (campo) mandarAlteracao(campo); // a resposta troca o pedido inteiro, já fechado
    }
  });

  // − e + da quantidade (resultados e pedido): o servidor revalida. Mexem
  // na parte inteira (",5" conta como 0) e nunca a levam abaixo de 1: o − que passaria disso
  // não faz nada, em vez de virar aumento ("0,5" − nunca vira "1,5").
  document.addEventListener("click", function (e) {
    var botao = e.target.closest && e.target.closest("[data-quantidade]");
    if (!botao) return;
    var campo = botao.parentNode.querySelector(".quantidade-campo");
    if (!campo) return;
    var valor = campo.value || "";
    var virgula = valor.indexOf(",");
    var inteiro = parseInt(virgula >= 0 ? valor.slice(0, virgula) : valor, 10);
    if (isNaN(inteiro)) inteiro = 0;
    var resto = virgula >= 0 ? valor.slice(virgula) : "";
    var novo = inteiro + (botao.getAttribute("data-quantidade") === "mais" ? 1 : -1);
    if (novo < 1) {
      if (!resto) campo.value = "1";
      return;
    }
    campo.value = String(novo) + resto;
    // No pedido, o campo manda a alteração ao servidor no "change" (hx-trigger).
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  });

  // Quantidade entregue na tabela do atendimento (_recibo.html): o estado (total, parcial, não
  // entregue, acima do pedido) é só aviso na tela; quem decide é o servidor. Números em pt-BR:
  // vírgula decimal, sem separador de milhar.
  function lerQtd(texto) {
    var t = (texto || "").trim();
    return /^\d+(,\d+)?$/.test(t) ? parseFloat(t.replace(",", ".")) : NaN;
  }

  function formatarQtd(n) {
    return String(+n.toFixed(3)).replace(".", ",");
  }

  // `editado`: a pessoa mexeu no valor; a recusa do servidor (entrega-erro) era sobre o valor
  // anterior, então a marca sai.
  function atualizarEntrega(campo, editado) {
    var bloco = campo.closest(".entrega");
    if (!bloco) return;
    if (editado) {
      bloco.classList.remove("entrega-erro");
      // O número dá um pulinho a cada mudança (a animação reinicia a cada edição).
      campo.classList.remove("mudou");
      void campo.offsetWidth;
      campo.classList.add("mudou");
    }
    // Com a unidade dentro do campo, ele tem a largura dos dígitos, para os dois andarem juntos.
    if (campo.parentNode.querySelector(".entrega-un")) {
      campo.style.width = Math.max(1, campo.value.length) + "ch";
    }
    // Quatro caracteres ou mais ("12,5", "1000") não cabem na caixa na fonte cheia: a letra diminui.
    campo.classList.toggle("entrega-campo-longo", campo.value.length > 3);
    // Vazio é inválido, como no servidor: para não entregar, escreva 0.
    var valor = lerQtd(campo.value);
    var pedido = lerQtd(campo.getAttribute("data-pedido"));
    var estado;
    if (isNaN(valor)) estado = "invalido";
    else if (valor === 0) estado = "zero";
    // Acrescentado pelo almoxarifado: não tem quantidade pedida, então não há parcial nem acima
    // ("ok" não mostra texto de estado).
    else if (bloco.closest("tr[data-adicionado]")) estado = "ok";
    else if (valor > pedido) estado = "acima";
    else if (valor < pedido) estado = "parcial";
    else estado = "total";
    bloco.setAttribute("data-estado", estado);
    var faltam = bloco.querySelector("[data-faltam]");
    if (faltam && estado === "parcial") faltam.textContent = formatarQtd(pedido - valor);
  }

  document.addEventListener("input", function (e) {
    if (e.target.classList && e.target.classList.contains("entrega-campo")) atualizarEntrega(e.target, true);
  });

  document.addEventListener("click", function (e) {
    var passo = e.target.closest && e.target.closest("[data-entrega-passo]");
    if (passo) {
      var campo = passo.parentNode.querySelector(".entrega-campo");
      var valor = campo.value.trim() === "" ? 0 : lerQtd(campo.value);
      if (isNaN(valor)) valor = 0;
      var novo = valor + Number(passo.getAttribute("data-entrega-passo"));
      campo.value = formatarQtd(Math.max(0, novo));
      atualizarEntrega(campo, true);
      campo.focus();
      return;
    }
    if (e.target.closest && e.target.closest("[data-entregar-tudo]")) {
      // Só o que foi pedido: os acrescentados e os itens trocados ficam como estão.
      document.querySelectorAll(".entrega-campo").forEach(function (campo) {
        if (campo.closest("tr[data-adicionado], tr[data-trocado], tr[data-em-troca]")) return;
        campo.value = campo.getAttribute("data-pedido");
        atualizarEntrega(campo, true);
        confirmarEntrega(campo.closest(".entrega"));
      });
      avisarPendentes();
      return;
    }
    var confirmar = e.target.closest && e.target.closest("[data-entrega-confirmar]");
    if (confirmar) {
      var bloco = confirmar.closest(".entrega");
      if (confirmarEntrega(bloco)) irParaProximaEntrega(bloco);
      return;
    }
    var alterar = e.target.closest && e.target.closest("[data-entrega-alterar]");
    if (alterar) reabrirEntrega(alterar.closest(".entrega"));
  });

  // Cada quantidade entregue é confirmada antes do envio (data-confirmado na .entrega): confirmada,
  // o campo fica só leitura, o − e o + somem e a caixa vira o "Alterar" (lápis). Sem JavaScript, nada disso existe e o campo vale como está.
  function confirmarEntrega(bloco) {
    if (!bloco) return false;
    var campo = bloco.querySelector(".entrega-campo");
    // Inválido ou acima do pedido não se confirma: o servidor recusaria. Nem o acrescentado com 0
    // (acrescentar sem entregar não tem sentido; para desistir dele, "Remover" ou "Desfazer troca").
    var estado = bloco.getAttribute("data-estado");
    var adicionadoZero = estado === "zero" && bloco.closest("tr[data-adicionado]");
    if (estado === "invalido" || estado === "acima" || adicionadoZero) {
      campo.focus();
      return false;
    }
    bloco.setAttribute("data-confirmado", "");
    campo.readOnly = true;
    campo.tabIndex = -1; // quem recebe o Tab é a caixa (o "Alterar" que a cobre), não o número
    bloco.querySelector("[data-entrega-confirmar]").hidden = true;
    bloco.querySelector("[data-entrega-alterar]").hidden = false;
    avisarPendentes();
    return true;
  }

  function reabrirEntrega(bloco, semFoco) {
    // O item trocado fica com 0 até a troca ser desfeita ("Desfazer troca" tira a marca antes), e o
    // item em troca, até o painel fechar.
    if (bloco.closest("tr[data-trocado], tr[data-em-troca]")) return;
    var campo = bloco.querySelector(".entrega-campo");
    bloco.removeAttribute("data-confirmado");
    campo.readOnly = false;
    campo.removeAttribute("tabindex");
    bloco.querySelector("[data-entrega-confirmar]").hidden = false;
    bloco.querySelector("[data-entrega-alterar]").hidden = true;
    if (semFoco) return;
    // Foco com o cursor no fim, sem selecionar o número: o − e o + voltam para ajustar.
    campo.focus();
    var fim = campo.value.length;
    campo.setSelectionRange(fim, fim);
  }

  function entregasPendentes() {
    return Array.prototype.slice.call(document.querySelectorAll(".entrega[data-pode-confirmar]:not([data-confirmado])"));
  }

  // Depois de confirmar, o foco vai para o próximo material ainda sem confirmação (ou, se não há
  // mais nenhum, para a data da saída).
  function irParaProximaEntrega(bloco) {
    var todos = Array.prototype.slice.call(document.querySelectorAll(".entrega[data-pode-confirmar]"));
    var depois = todos.slice(todos.indexOf(bloco) + 1).concat(todos.slice(0, todos.indexOf(bloco)));
    var proximo = depois.filter(function (b) { return !b.hasAttribute("data-confirmado"); })[0];
    var alvo = proximo ? proximo.querySelector(".entrega-campo") : document.getElementById("data");
    if (alvo) {
      alvo.focus();
      if (alvo.select) alvo.select();
    }
  }

  // O aviso dos pendentes só aparece depois de uma tentativa de envio, e some (ou se atualiza) à
  // medida que as quantidades são confirmadas.
  function avisarPendentes(tentouEnviar) {
    var caixa = document.querySelector("[data-entrega-pendentes]");
    if (!caixa || (caixa.hidden && !tentouEnviar)) return;
    var n = entregasPendentes().length;
    caixa.hidden = n === 0;
    caixa.textContent =
      n === 1
        ? "Falta confirmar a quantidade entregue de 1 material antes de registrar a saída."
        : "Falta confirmar a quantidade entregue de " + n + " materiais antes de registrar a saída.";
  }

  // Envio com quantidade sem confirmar: para e leva ao primeiro material pendente. A conferência vem
  // no clique do botão, antes da validação do navegador (senão "preencha o recebedor" viria antes),
  // e de novo no submit (Enter num campo do formulário). Troca aberta também barra: o trocado já
  // está confirmado com 0, e o envio registraria a saída sem o material que o substitui.
  function barrarPendentes(e) {
    var emTroca = document.querySelector("tr[data-em-troca]");
    if (emTroca) {
      e.preventDefault();
      var caixa = document.querySelector("[data-entrega-pendentes]");
      if (caixa) {
        caixa.hidden = false;
        caixa.textContent = "Termine ou cancele a troca de " + nomeDaLinha(emTroca) + " antes de registrar a saída.";
      }
      var busca = document.getElementById("atendimento-q");
      if (busca) {
        busca.scrollIntoView({ block: "center" });
        busca.focus();
      }
      return;
    }
    var pendentes = entregasPendentes();
    if (!pendentes.length) return;
    e.preventDefault();
    avisarPendentes(true);
    var campo = pendentes[0].querySelector(".entrega-campo");
    campo.scrollIntoView({ block: "center" });
    campo.focus();
    campo.select();
  }
  document.addEventListener("click", function (e) {
    var botao = e.target.closest && e.target.closest("button[type=submit], input[type=submit]");
    if (botao && botao.form && botao.form.id === "form-atendimento") barrarPendentes(e);
  });
  document.addEventListener("submit", function (e) {
    if (e.target.id === "form-atendimento") barrarPendentes(e);
  });

  // Enter numa quantidade confirma e pula para a próxima sem confirmação (e, na última, para a data
  // da saída), em vez de enviar o atendimento sem os outros campos conferidos.
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || !e.target.classList || !e.target.classList.contains("entrega-campo")) return;
    e.preventDefault();
    var bloco = e.target.closest(".entrega");
    if (bloco.hasAttribute("data-confirmado") || confirmarEntrega(bloco)) irParaProximaEntrega(bloco);
  });

  function iniciarEntrega(campo) {
    atualizarEntrega(campo, false);
    var bloco = campo.closest(".entrega");
    var confirmar = bloco.querySelector("[data-entrega-confirmar]");
    if (!confirmar) return;
    bloco.setAttribute("data-pode-confirmar", "");
    if (!bloco.hasAttribute("data-confirmado")) confirmar.hidden = false;
  }

  function iniciarEntregas() {
    document.querySelectorAll(".entrega-campo").forEach(iniciarEntrega);
  }
  document.addEventListener("DOMContentLoaded", iniciarEntregas);

  // Troca e acréscimo de material no atendimento (_recibo.html, _adicionado.html). "Trocar" (em
  // cada material pedido) abre o painel de busca numa linha logo abaixo dele; "Adicionar material"
  // o abre no lugar dele, abaixo da tabela. O "Adicionar" dos resultados junta a linha nova ao
  // `#adicionados`; aí o painel fecha e, na troca, o item pedido vai para 0, confirmado ("Não
  // entregue"), com "Trocado por …" (a quantidade de antes fica em `data-qtd-antes`, para o
  // "Desfazer troca"). Cada mudança é anunciada no `role="status"` da tabela. Sem JavaScript, nada
  // disso aparece e o atendimento funciona como antes.
  function painelAtendimento() {
    return document.querySelector("[data-atendimento-painel]");
  }

  var marcaDoPainel = null; // onde o painel fica no HTML, para voltar ao fechar
  var abridorDoPainel = null;

  function nomeDaLinha(linha) {
    var nome = linha && linha.querySelector("td:first-child strong");
    return nome ? nome.textContent.trim() : "";
  }

  function linhaPedida(codigo) {
    var botao = codigo && document.querySelector('[data-trocar="' + CSS.escape(codigo) + '"]');
    return botao ? botao.closest("tr") : null;
  }

  function anunciarAtendimento(texto) {
    var regiao = document.querySelector("[data-anuncio-atendimento]");
    if (!regiao) {
      var tabela = document.querySelector(".recibo-itens");
      if (!tabela) return;
      regiao = document.createElement("p");
      regiao.className = "visually-hidden";
      regiao.setAttribute("role", "status");
      regiao.setAttribute("aria-atomic", "true");
      regiao.setAttribute("data-anuncio-atendimento", "");
      tabela.closest(".tabela-rolagem").after(regiao);
    }
    // Esvazia antes, para a mesma frase repetida ser anunciada de novo. Com `setTimeout`, não
    // `requestAnimationFrame`: este não roda com a janela minimizada ou a aba em segundo plano.
    regiao.textContent = "";
    setTimeout(function () {
      regiao.textContent = texto;
    }, 50);
  }

  function contarMateriais() {
    var titulo = document.querySelector("[data-contagem-materiais]");
    if (!titulo) return;
    titulo.textContent = "Materiais (" + document.querySelectorAll(".recibo-itens .entrega-campo").length + ")";
  }

  // Na linha da tabela, o painel tem no máximo a largura visível da rolagem e fica preso à esquerda
  // (pedidos.css): no celular, a tabela rola de lado e o painel não.
  function ajustarLarguraPainel() {
    var form = painelAtendimento();
    var rolagem = form && form.closest(".tabela-rolagem");
    if (rolagem) form.style.setProperty("--painel-largura", rolagem.clientWidth + "px");
  }
  window.addEventListener("resize", ajustarLarguraPainel);

  function fecharPainelAtendimento(devolverFoco) {
    var form = painelAtendimento();
    if (!form || form.hidden) return;
    form.hidden = true;
    var linha = form.closest(".atendimento-painel-linha");
    if (marcaDoPainel) marcaDoPainel.after(form);
    if (linha) {
      var emTroca = linha.previousElementSibling;
      linha.remove();
      if (emTroca && emTroca.hasAttribute("data-em-troca")) {
        emTroca.removeAttribute("data-em-troca");
        if (!emTroca.hasAttribute("data-trocado")) devolverQtdAntes(emTroca);
        // O aviso de troca aberta (barrarPendentes) dá lugar ao dos pendentes, ou some.
        avisarPendentes();
      }
    }
    var abridor = abridorDoPainel;
    abridorDoPainel = null;
    if (!abridor) return;
    abridor.setAttribute("aria-expanded", "false");
    if (abridor.hasAttribute("data-trocar")) abridor.setAttribute("aria-label", "Trocar " + nomeDaLinha(abridor.closest("tr")));
    if (devolverFoco && abridor.isConnected && !abridor.hidden) abridor.focus();
  }

  // `trocado`: a linha do material pedido que será trocado; sem ela, é um acréscimo.
  function abrirPainelAtendimento(abridor, trocado) {
    var form = painelAtendimento();
    if (!form) return;
    fecharPainelAtendimento(false);
    if (!marcaDoPainel) {
      marcaDoPainel = document.createComment("painel da troca e do acréscimo");
      form.before(marcaDoPainel);
      // A recusa do "Adicionar" aparece dentro do painel, perto de quem adicionou.
      var erro = document.getElementById("adicionar-erro");
      var acoes = form.querySelector(".acoes");
      if (erro && acoes) acoes.before(erro);
    }
    var nome = nomeDaLinha(trocado);
    form.querySelector("[name=no_lugar_de]").value = trocado ? trocado.querySelector("[data-trocar]").getAttribute("data-trocar") : "";
    form.querySelector("[data-painel-titulo]").textContent = trocado ? "Trocar " + nome + " por:" : "Adicionar material";
    form.querySelector("[data-painel-frase]").hidden = !trocado;
    // Na troca, quem fecha é o próprio botão da linha ("Cancelar troca"); o "Desistir" é do acréscimo.
    form.querySelector("[data-painel-desistir]").closest(".acoes").hidden = !!trocado;
    if (trocado) abridor.setAttribute("aria-label", "Cancelar troca de " + nome);
    if (trocado) {
      var linha = document.createElement("tr");
      linha.className = "atendimento-painel-linha nao-imprimir";
      var celula = document.createElement("td");
      var colunas = 0;
      Array.prototype.forEach.call(trocado.cells, function (c) { colunas += c.colSpan; });
      celula.colSpan = colunas;
      celula.appendChild(form);
      linha.appendChild(celula);
      trocado.after(linha);
      zerarParaTroca(trocado);
      trocado.setAttribute("data-em-troca", "");
    }
    // Busca, resultados e recusa da vez anterior não valem para esta.
    var busca = form.querySelector("#atendimento-q");
    busca.value = "";
    form.querySelector("#atendimento-resultados").innerHTML = "";
    var aviso = document.getElementById("adicionar-erro");
    if (aviso) aviso.textContent = "";
    form.hidden = false;
    ajustarLarguraPainel();
    abridorDoPainel = abridor;
    abridor.setAttribute("aria-expanded", "true");
    busca.focus();
    form.scrollIntoView({ block: "nearest" });
  }

  // Com a troca aberta, o item já aparece como ficará: 0 entregue e confirmado. A quantidade de
  // antes (`data-qtd-antes`, a mesma do "Desfazer troca") e a confirmação voltam se a troca for
  // cancelada.
  function zerarParaTroca(trocado) {
    var campo = trocado.querySelector(".entrega-campo");
    var bloco = campo.closest(".entrega");
    trocado.setAttribute("data-qtd-antes", campo.value);
    trocado.toggleAttribute("data-confirmado-antes", bloco.hasAttribute("data-confirmado"));
    campo.value = "0";
    atualizarEntrega(campo, true);
    if (!bloco.hasAttribute("data-confirmado")) confirmarEntrega(bloco);
  }

  function devolverQtdAntes(trocado) {
    var campo = trocado.querySelector(".entrega-campo");
    var bloco = campo.closest(".entrega");
    campo.value = trocado.getAttribute("data-qtd-antes");
    trocado.removeAttribute("data-qtd-antes");
    atualizarEntrega(campo, true);
    if (!trocado.hasAttribute("data-confirmado-antes")) reabrirEntrega(bloco, true);
    trocado.removeAttribute("data-confirmado-antes");
    avisarPendentes();
  }

  // O item pedido trocado: 0 entregue e confirmado (ao vivo; na página devolvida pelo servidor,
  // fica com o valor enviado), a nota "Trocado por …" e sem o "Trocar".
  function marcarTrocado(trocado, novo, aoVivo) {
    var campo = trocado.querySelector(".entrega-campo");
    var bloco = campo.closest(".entrega");
    trocado.setAttribute("data-trocado", "");
    trocado.removeAttribute("data-confirmado-antes");
    trocado.querySelector("[data-trocar]").hidden = true;
    if (!trocado.hasAttribute("data-qtd-antes")) {
      trocado.setAttribute("data-qtd-antes", aoVivo ? campo.value : campo.getAttribute("data-pedido"));
    }
    if (aoVivo) {
      campo.value = "0";
      atualizarEntrega(campo, true);
    }
    if (!bloco.hasAttribute("data-confirmado")) confirmarEntrega(bloco);
    if (!trocado.querySelector("[data-trocado-por]")) {
      var nota = document.createElement("span");
      nota.className = "recibo-nota";
      nota.setAttribute("data-trocado-por", "");
      nota.textContent = "Trocado por " + nomeDaLinha(novo);
      trocado.cells[0].appendChild(nota);
    }
  }

  // Linha acrescentada (vinda da busca, ou devolvida pelo servidor na recusa do envio): confirmação
  // como as outras, o "Remover" ou o "Desfazer troca" à vista e a troca aplicada ao item pedido.
  // Devolve a linha do item trocado, se houver.
  function iniciarAdicionado(linha, aoVivo) {
    linha.setAttribute("data-iniciado", "");
    iniciarEntrega(linha.querySelector(".entrega-campo"));
    var desfazer = linha.querySelector("[data-desfazer-troca], [data-remover-adicionado]");
    if (desfazer) desfazer.hidden = false;
    var trocado = linhaPedida(linha.getAttribute("data-no-lugar-de"));
    if (trocado) marcarTrocado(trocado, linha, aoVivo);
    return trocado;
  }

  function iniciarTrocas() {
    if (!painelAtendimento()) return;
    document.querySelectorAll("[data-trocar], [data-adicionar-material]").forEach(function (botao) {
      botao.hidden = false;
      botao.setAttribute("aria-expanded", "false");
    });
    document.querySelectorAll("#adicionados tr[data-adicionado]").forEach(function (linha) {
      iniciarAdicionado(linha, false);
    });
    contarMateriais();
  }
  document.addEventListener("DOMContentLoaded", iniciarTrocas);

  // A linha nova chega pelo `hx-swap="beforeend"` no `#adicionados`; uma recusa vai para o
  // `#adicionar-erro` e o painel fica aberto para outra escolha.
  document.addEventListener("htmx:after:swap", function () {
    var novas = document.querySelectorAll("#adicionados tr[data-adicionado]:not([data-iniciado])");
    if (!novas.length) return;
    var linha = novas[novas.length - 1];
    var trocado = null;
    novas.forEach(function (nova) {
      var t = iniciarAdicionado(nova, true);
      if (nova === linha) trocado = t;
    });
    fecharPainelAtendimento(false);
    var aviso = document.getElementById("adicionar-erro");
    if (aviso) aviso.textContent = "";
    contarMateriais();
    avisarPendentes();
    var campo = linha.querySelector(".entrega-campo");
    campo.focus();
    var fim = campo.value.length;
    campo.setSelectionRange(fim, fim);
    anunciarAtendimento(
      trocado
        ? nomeDaLinha(linha) + " entrou no lugar de " + nomeDaLinha(trocado) + "."
        : nomeDaLinha(linha) + " foi adicionado."
    );
  });

  function removerAdicionado(linha) {
    var nome = nomeDaLinha(linha);
    linha.remove();
    contarMateriais();
    avisarPendentes();
    var adicionar = document.querySelector("[data-adicionar-material]");
    if (adicionar) adicionar.focus();
    anunciarAtendimento(nome + " foi removido.");
  }

  // Tira o acrescentado e devolve ao item pedido a quantidade de antes da troca, por confirmar.
  function desfazerTroca(linha) {
    var trocado = linhaPedida(linha.getAttribute("data-no-lugar-de"));
    linha.remove();
    contarMateriais();
    if (!trocado) return avisarPendentes();
    var campo = trocado.querySelector(".entrega-campo");
    var antes = trocado.getAttribute("data-qtd-antes");
    campo.value = antes === null ? campo.getAttribute("data-pedido") : antes;
    trocado.removeAttribute("data-qtd-antes");
    trocado.removeAttribute("data-trocado");
    var nota = trocado.querySelector("[data-trocado-por]");
    if (nota) nota.remove();
    trocado.querySelector("[data-trocar]").hidden = false;
    atualizarEntrega(campo, true);
    reabrirEntrega(campo.closest(".entrega")); // o foco vai para a quantidade dele
    avisarPendentes();
    anunciarAtendimento("Troca desfeita: " + nomeDaLinha(trocado) + " voltou ao pedido.");
  }

  document.addEventListener("click", function (e) {
    var alvo = e.target;
    if (!alvo || !alvo.closest) return;
    var trocar = alvo.closest("[data-trocar]");
    if (trocar) {
      if (trocar.getAttribute("aria-expanded") === "true") return fecharPainelAtendimento(true);
      return abrirPainelAtendimento(trocar, trocar.closest("tr"));
    }
    var adicionar = alvo.closest("[data-adicionar-material]");
    if (adicionar) return abrirPainelAtendimento(adicionar, null);
    if (alvo.closest("[data-painel-desistir]")) return fecharPainelAtendimento(true);
    var remover = alvo.closest("[data-remover-adicionado]");
    if (remover) return removerAdicionado(remover.closest("tr"));
    var desfazer = alvo.closest("[data-desfazer-troca]");
    if (desfazer) desfazerTroca(desfazer.closest("tr"));
  });

  // Esc no painel o fecha, como o "Desistir".
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !e.target.closest || !e.target.closest("[data-atendimento-painel]")) return;
    e.preventDefault();
    fecharPainelAtendimento(true);
  });

  // Falha de rede ou do servidor no envio: o formulário fica (o htmx-config não troca o
  // conteúdo em 4xx/5xx) e a pessoa é avisada de que reenviar não duplica. A caixa fica no
  // topo do formulário: rola até ela, porque quem enviou está no fim da página.
  function avisarFalha(e) {
    var alvo = e.target;
    var form = alvo && alvo.matches && alvo.matches("[data-formulario-pedido]") ? alvo : null;
    var caixa = form && form.querySelector("[data-erro-envio]");
    if (!caixa) return;
    caixa.className = "aviso aviso-erro";
    caixa.textContent =
      "Não foi possível enviar. O formulário foi mantido; ao tentar de novo, o sistema " +
      "confere se o pedido já foi gravado e não duplica.";
    caixa.scrollIntoView({ block: "center" });
  }
  document.addEventListener("htmx:error", avisarFalha);
  document.addEventListener("htmx:response:error", avisarFalha);

  // Envio recusado (_formulario.html): o foco vai para o resumo dos erros, para o leitor de tela
  // anunciá-lo (o `show:top` do HTMX já rolou até ele). Corrigir um campo marcado tira a marca
  // (a mensagem embaixo dele fica até o próximo envio).
  document.addEventListener("htmx:after:swap", function () {
    var resumo = document.querySelector("[data-formulario-pedido] [data-resumo-erros]");
    if (resumo && !resumo.hasAttribute("data-focado")) {
      resumo.setAttribute("data-focado", "");
      resumo.focus({ preventScroll: true });
    }
  });

  function desmarcarErro(e) {
    var campo = e.target;
    if (!campo || !campo.matches || !campo.matches('[data-formulario-pedido] [aria-invalid="true"]')) {
      return;
    }
    campo.removeAttribute("aria-invalid");
    var bloco = campo.closest(".campo");
    if (bloco) bloco.classList.remove("campo-com-erro");
  }
  document.addEventListener("input", desmarcarErro);
  document.addEventListener("change", desmarcarErro); // escolha na lista do dropdown.js

  document.addEventListener("click", function (e) {
    // "Quem recebe é o solicitante" preenche o recebedor.
    var botao = e.target.closest && e.target.closest("[data-preencher-recebedor]");
    if (!botao) return;
    var campo = document.getElementById("recebedor");
    if (!campo) return;
    campo.value = botao.getAttribute("data-nome");
    // "change", não "input": o input abriria a lista do dropdown.js.
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  });

  // O atalho só aparece com o recebedor vazio: preenchido, o nome usa a largura toda do campo
  // (o CSS só reserva o espaço do botão enquanto ele está à vista).
  function sincronizarAtalhoRecebedor() {
    var campo = document.getElementById("recebedor");
    var botao = document.querySelector("[data-preencher-recebedor]");
    if (campo && botao) botao.hidden = campo.value.trim() !== "";
  }
  document.addEventListener("input", function (e) {
    if (e.target.id === "recebedor") sincronizarAtalhoRecebedor();
  });
  document.addEventListener("change", function (e) {
    if (e.target.id === "recebedor") sincronizarAtalhoRecebedor();
  });
  document.addEventListener("DOMContentLoaded", sincronizarAtalhoRecebedor);
  document.addEventListener("htmx:after:swap", sincronizarAtalhoRecebedor);

  // A placa decide o centro de custo (regra do robô): com um veículo escolhido, o centro vira o
  // dele e o dropdown fica travado. O <select> segue habilitado, porque campo desabilitado não
  // vai no envio e o servidor confere o centro. `data-travado` é lido pelo dropdown.js.
  function sincronizarCentro() {
    var placa = document.getElementById("placa");
    var cc = document.getElementById("centro_custo");
    if (!placa || !cc) return;
    var opcao = placa.selectedOptions[0];
    var centro = (placa.value && opcao && opcao.getAttribute("data-centro")) || "";
    if (centro) {
      cc.value = centro;
      // O dropdown redesenha o valor ao ouvir o change.
      cc.dispatchEvent(new Event("change", { bubbles: true }));
    }
    cc.toggleAttribute("data-travado", !!centro);
    var dica = document.getElementById("centro_custo-dica");
    if (dica) dica.hidden = !centro;
  }

  document.addEventListener("change", function (e) {
    if (e.target.id === "placa") sincronizarCentro();
  });
  document.addEventListener("DOMContentLoaded", sincronizarCentro);
  document.addEventListener("htmx:after:swap", sincronizarCentro);

  // Depois de imprimir (pelo botão ou pelo Ctrl+P), abre o diálogo de confirmação
  // (`dialog[data-apos-imprimir]`, dialogo.js) que pergunta se os recibos saíram na impressora; antes
  // disso, marcar como impressos não faz sentido. "Ainda não" (ou Esc) só o fecha: ele volta a abrir
  // na próxima impressão, e o recibo segue na lista de pendentes.
  function revelarConfirmacao() {
    var dialogo = document.querySelector("dialog[data-apos-imprimir]");
    if (!dialogo || dialogo.open) return;
    dialogo.showModal();
  }
  window.addEventListener("afterprint", revelarConfirmacao);
  document.addEventListener("DOMContentLoaded", function () {
    // O botão de imprimir só funciona com JavaScript: sem ele, fica escondido.
    document.querySelectorAll("[data-imprimir][hidden]").forEach(function (b) { b.hidden = false; });
  });

  document.addEventListener("click", function (e) {
    var botao = e.target.closest && e.target.closest("[data-imprimir]");
    if (!botao) return;
    window.print();
    revelarConfirmacao();
  });

  // O pedido em montagem só existe na página: sair dela (link, voltar, fechar) com material no
  // pedido pede confirmação. O envio sem HTMX (sem JavaScript não há aviso) e a tela de sucesso,
  // que já não tem o carrinho, saem direto. A saída avulsa não tem `data-formulario-pedido`.
  var enviando = false;
  document.addEventListener("submit", function (e) {
    if (!e.target.querySelectorAll) return;
    // Quantidade do pedido aberta e não confirmada não vale: vai a que estava (também na saída
    // avulsa).
    e.target.querySelectorAll("[data-alterar].aberto").forEach(cancelarAlteracao);
    if (e.target.matches("[data-formulario-pedido]")) enviando = true;
  });
  document.addEventListener("htmx:after:request", function () {
    enviando = false;
  });
  window.addEventListener("beforeunload", function (e) {
    if (enviando) return;
    if (!document.querySelector("[data-formulario-pedido] .carrinho-linha[data-codigo]")) return;
    e.preventDefault();
    e.returnValue = "";
  });

  // Nome e destino lembrados neste aparelho (só neste navegador, nunca no servidor). O nome é
  // gravado enquanto se digita; a tela de sucesso (`data-lembrar-*`) grava os dois. O formulário
  // novo preenche os campos que estiverem vazios (o destino só se ainda estiver na lista). Cada campo
  // tem o seu "Limpar" (`data-limpar-campo`), visível enquanto ele tem valor, que apaga o campo e o
  // que ficou lembrado dele. Sem armazenamento (aba anônima, bloqueado), nada é lembrado.
  var CHAVE_LEMBRADO = "almoxarifado.solicitante";

  function lerLembrado() {
    var dados = null;
    try { dados = JSON.parse(window.localStorage.getItem(CHAVE_LEMBRADO)); } catch (e) { dados = null; }
    return dados && typeof dados === "object" ? dados : null;
  }

  function gravarLembrado(dados) {
    try { window.localStorage.setItem(CHAVE_LEMBRADO, JSON.stringify(dados)); } catch (e) { /* sem armazenamento */ }
  }

  function esquecerLembrado() {
    try { window.localStorage.removeItem(CHAVE_LEMBRADO); } catch (e) { /* sem armazenamento */ }
  }

  // Só "change": um "input" faria o dropdown.js abrir a lista de sugestões sem ninguém pedir.
  function preencher(campo, valor) {
    campo.value = valor;
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function aplicarLembrado() {
    var sucesso = document.querySelector("[data-lembrar-solicitante]");
    if (sucesso) {
      gravarLembrado({
        solicitante: sucesso.getAttribute("data-lembrar-solicitante"),
        destino: sucesso.getAttribute("data-lembrar-destino"),
      });
      return;
    }
    var form = document.querySelector("[data-formulario-pedido]");
    if (!form) return;
    mostrarLimpar(form);
    // Só no formulário novo: depois de um envio recusado, os campos ficam como a pessoa deixou.
    if (form.hasAttribute("data-lembrado-aplicado")) return;
    if (form.querySelector("[data-resumo-erros]")) return;
    form.setAttribute("data-lembrado-aplicado", "");
    var dados = lerLembrado();
    if (!dados) return;
    var nome = form.querySelector("#solicitante");
    var destino = form.querySelector("#destino");
    if (nome && !nome.value && typeof dados.solicitante === "string" && dados.solicitante) {
      preencher(nome, dados.solicitante);
    }
    var opcoes = Array.prototype.map.call(document.querySelectorAll("#destinos option"), function (o) {
      return o.value;
    });
    if (destino && !destino.value && opcoes.indexOf(dados.destino) !== -1) {
      preencher(destino, dados.destino);
    }
  }

  // O "Limpar" de cada campo só aparece com o campo preenchido.
  function mostrarLimpar(form) {
    Array.prototype.forEach.call(form.querySelectorAll("[data-limpar-campo]"), function (botao) {
      var campo = form.querySelector("#" + botao.getAttribute("data-limpar-campo"));
      botao.hidden = !campo || !campo.value;
    });
  }

  document.addEventListener("DOMContentLoaded", aplicarLembrado);
  document.addEventListener("htmx:after:swap", aplicarLembrado);

  // O último nome escrito, mesmo sem enviar o pedido; apagar o campo esquece o nome.
  document.addEventListener("input", function (e) {
    var nome = e.target;
    var formulario = nome.closest && nome.closest("[data-formulario-pedido]");
    if (formulario) mostrarLimpar(formulario);
    if (nome.id !== "solicitante" || !formulario) return;
    var dados = lerLembrado() || {};
    var valor = nome.value.trim();
    if (valor) dados.solicitante = valor;
    else delete dados.solicitante;
    if (dados.solicitante || dados.destino) gravarLembrado(dados);
    else esquecerLembrado();
  });

  // Escolher um destino na lista dispara só "change".
  document.addEventListener("change", function (e) {
    var form = e.target.closest && e.target.closest("[data-formulario-pedido]");
    if (form) mostrarLimpar(form);
  });

  document.addEventListener("click", function (e) {
    var botao = e.target.closest && e.target.closest("[data-limpar-campo]");
    if (!botao) return;
    var form = botao.closest("[data-formulario-pedido]");
    var chave = botao.getAttribute("data-limpar-campo");
    var campo = form && form.querySelector("#" + chave);
    if (!campo) return;
    preencher(campo, "");
    var dados = lerLembrado() || {};
    delete dados[chave];
    if (dados.solicitante || dados.destino) gravarLembrado(dados);
    else esquecerLembrado();
    campo.focus();
  });

  // "Seu pedido" (_resumo_pedido.html, _carrinho.html). Sem largura para a coluna ao lado dos
  // passos (menos de 960px, o mesmo limite do @container de pedidos.css), uma barra fixa abre a
  // gaveta (<dialog>, que já prende o foco e fecha com Esc); o <html> ganha `data-gaveta`, que o
  // CSS lê. A barra e a
  // gaveta vêm no trecho #carrinho que o HTMX troca a cada Adicionar/Remover: o estado aberto é
  // lembrado entre as trocas, e um erro ou aviso novo abre a gaveta, senão quem adicionou não
  // veria o motivo.
  var LARGURA_LADO_A_LADO = 960;
  var reabrir = false;
  var observador = null;
  var observado = null;

  function gavetaAtiva() {
    return document.documentElement.hasAttribute("data-gaveta");
  }

  // A área dos passos muda de largura com a janela e com a barra lateral; as trocas do HTMX
  // podem substituí-la, então a observação é refeita a cada troca.
  function observarPasso() {
    if (!window.ResizeObserver) return;
    var area = document.querySelector(".pedido-layout");
    if (area === observado) return;
    if (observador) observador.disconnect();
    observado = area;
    if (!area) return;
    observador = new ResizeObserver(function (entradas) {
      var compacto = entradas[0].contentRect.width < LARGURA_LADO_A_LADO;
      document.documentElement.toggleAttribute("data-gaveta", compacto);
      // A largura mudou, e com ela a quebra dos nomes: o painel de resultados é medido de novo.
      agendarAjuste();
      if (compacto) return;
      fecharGaveta();
    });
    observador.observe(area);
  }

  function gaveta() {
    return document.getElementById("carrinho-gaveta");
  }

  // Envio pela gaveta (formulários públicos e saída avulsa): o botão da gaveta não é de envio; ele
  // aciona o botão do fim do formulário, que tem o rótulo certo (o do caso divergente) e, nos
  // formulários públicos, passa pelo HTMX.
  function botaoFinal() {
    return document.querySelector(".acoes-final button[type=submit]");
  }

  function copiarRotuloDoEnvio() {
    var final = botaoFinal();
    var rotulo = document.querySelector("[data-carrinho-enviar-rotulo]");
    if (final && rotulo) rotulo.textContent = final.textContent.trim();
  }

  function enviarPelaGaveta() {
    var final = botaoFinal();
    if (!final) return;
    fecharGaveta(); // a resposta (sucesso ou erros) aparece na página, não atrás da gaveta
    if (final.form.requestSubmit) final.form.requestSubmit(final);
    else final.click();
  }

  function abrirGaveta() {
    var g = gaveta();
    if (!g || g.open || !g.showModal || !gavetaAtiva()) return;
    copiarRotuloDoEnvio();
    g.showModal();
    var botao = document.querySelector("[data-carrinho-abrir]");
    if (botao) botao.setAttribute("aria-expanded", "true");
  }

  function fecharGaveta() {
    var g = gaveta();
    if (g && g.open) g.close();
  }

  // "close" não sobe pelo DOM; a captura em `document` pega o Esc e o fechar pelo botão.
  document.addEventListener(
    "close",
    function (e) {
      if (e.target.id !== "carrinho-gaveta") return;
      var botao = document.querySelector("[data-carrinho-abrir]");
      if (!botao) return;
      botao.setAttribute("aria-expanded", "false");
      if (document.activeElement === document.body) botao.focus();
    },
    true
  );

  document.addEventListener("click", function (e) {
    var alvo = e.target;
    if (!alvo || !alvo.closest) return;
    if (alvo.closest("[data-carrinho-abrir]")) return abrirGaveta();
    if (alvo.closest("[data-carrinho-fechar]")) return fecharGaveta();
    if (alvo.closest("[data-carrinho-enviar]")) return enviarPelaGaveta();
    if (alvo.closest("[data-carrinho-continuar]")) {
      var passo = alvo.closest(".passo");
      fecharGaveta();
      var proximo = passo && passo.nextElementSibling;
      if (proximo) proximo.scrollIntoView({ block: "start" });
      return;
    }
    // Clique no fundo escurecido (fora da caixa da gaveta) fecha.
    var g = gaveta();
    if (g && g.open && alvo === g) {
      var r = g.getBoundingClientRect();
      if (e.clientY < r.top || e.clientY > r.bottom || e.clientX < r.left || e.clientX > r.right) {
        fecharGaveta();
      }
    }
  });

  function atualizarPedido() {
    var carrinho = document.querySelector("[data-carrinho]");
    // "Alterar (N)" nos resultados que já estão no pedido.
    document.querySelectorAll("#resultados [data-codigo]").forEach(rotularAbrir);
    if (!carrinho || carrinho.hasAttribute("data-visto")) return;
    // Trecho novo do carrinho: reabre a gaveta, abre para um alerta e pulsa a barra.
    var primeiraVez = !document.documentElement.hasAttribute("data-pedido-visto");
    carrinho.setAttribute("data-visto", "");
    // O HTMX 4 troca por "morph" e preserva o valor digitado no campo; o que vale é o que o
    // servidor devolveu (a quantidade aceita, ou a anterior quando a alteração foi recusada).
    carrinho.querySelectorAll("[data-qtd-carrinho]").forEach(function (campo) {
      campo.value = campo.defaultValue;
    });
    document.documentElement.setAttribute("data-pedido-visto", "");
    if (reabrir || carrinho.querySelector("[data-carrinho-alerta]")) abrirGaveta();
    reabrir = false;
    var barra = carrinho.querySelector(".carrinho-barra");
    if (barra && !primeiraVez) barra.classList.add("carrinho-barra-pulso");
  }

  // Adicionar em dois passos (formulários públicos e saída avulsa, _resultados.html): tocar na linha do
  // material abre a quantidade (uma aberta por vez; tocar de novo na linha aberta a fecha), já com a do
  // pedido se ele estiver lá; "Confirmar" manda ao servidor como antes, e "Atualizar" (material já no
  // pedido) troca a quantidade da linha do pedido, sem somar. Esc ou o ✕ fecham. Com um aberto, as
  // outras linhas ficam recuadas (pedidos.css), mas clicáveis.
  var DURACAO_FEITO = 2000;

  function nomeDoMaterial(item) {
    var nome = item && item.querySelector(".material-titulo strong");
    return nome ? nome.textContent : "";
  }

  function campoNoPedido(item) {
    var codigo = item && item.getAttribute("data-codigo");
    var linhas = document.querySelectorAll("#carrinho .carrinho-linha[data-codigo]");
    for (var i = 0; i < linhas.length; i++) {
      if (linhas[i].getAttribute("data-codigo") === codigo) {
        return linhas[i].querySelector("[data-qtd-carrinho]");
      }
    }
    return null;
  }

  // Selo "N no pedido" de cada resultado (ao lado da informação do material) e o rótulo do botão que
  // abre a linha para o leitor de tela: com o material no pedido, "Alterar …, N no pedido".
  function rotularAbrir(item) {
    var abrir = item && item.querySelector("[data-adicionar-abrir]");
    if (!abrir) return;
    var noPedido = campoNoPedido(item);
    var nome = nomeDoMaterial(item);
    var selo = item.querySelector("[data-selo-pedido]");
    if (selo) {
      selo.hidden = !noPedido;
      if (noPedido) selo.querySelector("[data-selo-texto]").textContent = noPedido.defaultValue + " no pedido";
    }
    abrir.setAttribute(
      "aria-label",
      noPedido ? "Alterar " + nome + ", " + noPedido.defaultValue + " no pedido" : "Adicionar " + nome
    );
  }

  // O botão que abre a linha fica dentro do material (não da ação, que só existe aberta).
  function botaoDeAbrir(acao) {
    var item = acao && acao.closest("li");
    return item && item.querySelector("[data-adicionar-abrir]");
  }

  function fecharQuantidade(acao, devolverFoco) {
    if (!acao || !acao.classList.contains("aberto")) return;
    acao.classList.remove("aberto");
    var abrir = botaoDeAbrir(acao);
    if (!abrir) return;
    abrir.setAttribute("aria-expanded", "false");
    if (devolverFoco) abrir.focus();
  }

  function abrirQuantidade(acao) {
    fecharQuantidade(document.querySelector("[data-adicionar].aberto"), false);
    var item = acao.closest("li");
    var noPedido = campoNoPedido(item);
    var campo = acao.querySelector(".quantidade-campo");
    var confirmar = acao.querySelector("[data-adicionar-confirmar]");
    var rotulo = noPedido ? "Atualizar" : "Confirmar";
    campo.value = noPedido ? noPedido.value : "1";
    confirmar.textContent = rotulo;
    confirmar.setAttribute("aria-label", rotulo + " " + nomeDoMaterial(item));
    acao.toggleAttribute("data-atualizar", !!noPedido);
    acao.classList.add("aberto");
    botaoDeAbrir(acao).setAttribute("aria-expanded", "true");
    campo.focus();
    var fim = campo.value.length; // cursor no fim do número, sem selecioná-lo
    campo.setSelectionRange(fim, fim);
  }

  // Retorno de quem confirmou: o selo "no pedido" pisca por 2 s (nas linhas em dois passos, sem
  // botão) ou o botão do painel do atendimento mostra o feito; o leitor de tela ouve o nome do material.
  function mostrarFeito(item, botao, texto) {
    var anuncio = document.querySelector("[data-anuncio-adicionado]");
    var nome = nomeDoMaterial(item);
    if (anuncio && nome) anuncio.textContent = nome + (texto === "Adicionado" ? " adicionado." : ": quantidade atualizada.");
    if (!botao) {
      var selo = item && item.querySelector("[data-selo-pedido]");
      if (!selo) return;
      selo.classList.add("selo-pulso");
      clearTimeout(selo._voltar);
      selo._voltar = setTimeout(function () {
        selo.classList.remove("selo-pulso");
      }, DURACAO_FEITO);
      return;
    }
    if (!botao.hasAttribute("data-feito")) botao.setAttribute("data-original", botao.innerHTML);
    botao.setAttribute("data-feito", "");
    botao.textContent = texto; // sem ícone: cabe na largura fixa do botão (a linha não muda de altura)
    botao.classList.add("botao-adicionado");
    clearTimeout(botao._voltar);
    botao._voltar = setTimeout(function () {
      botao.innerHTML = botao.getAttribute("data-original");
      botao.removeAttribute("data-original");
      botao.removeAttribute("data-feito");
      botao.classList.remove("botao-adicionado");
      rotularAbrir(item);
    }, DURACAO_FEITO);
  }

  document.addEventListener("click", function (e) {
    var alvo = e.target;
    if (!alvo || !alvo.closest) return;
    var abrir = alvo.closest("[data-adicionar-abrir]");
    if (abrir) {
      var acao = abrir.closest("li").querySelector("[data-adicionar]");
      // Tocar de novo na linha aberta a fecha.
      return acao.classList.contains("aberto") ? fecharQuantidade(acao, true) : abrirQuantidade(acao);
    }
    var cancelar = alvo.closest("[data-adicionar-cancelar]");
    if (cancelar) fecharQuantidade(cancelar.closest("[data-adicionar]"), true);
  });

  // "Atualizar": a quantidade vai para a linha do pedido, que já manda a alteração ao servidor
  // ("change", que substitui em vez de somar). Na captura, antes de o HTMX mandar o "adicionar".
  document.addEventListener(
    "click",
    function (e) {
      var botao = e.target.closest && e.target.closest("[data-adicionar-confirmar]");
      var acao = botao && botao.closest("[data-adicionar]");
      if (!acao || !acao.hasAttribute("data-atualizar")) return;
      e.preventDefault();
      e.stopPropagation();
      var item = acao.closest("li");
      var noPedido = campoNoPedido(item);
      if (!noPedido) return;
      noPedido.value = acao.querySelector(".quantidade-campo").value;
      atualizando = { acao: acao, evento: mandarAlteracao(noPedido) };
    },
    true
  );

  // O "Atualizado" espera a resposta: aceita, a quantidade fecha e vem o retorno; recusada, ela
  // fica aberta para corrigir (o motivo aparece no pedido). Só a resposta da própria alteração
  // conta (o `sourceEvent` da requisição é o evento que a disparou); outras respostas passam.
  var atualizando = null;
  document.addEventListener("htmx:after:swap", function (e) {
    var pendente = atualizando;
    var ctx = e.detail && e.detail.ctx;
    if (!pendente || !ctx || ctx.sourceEvent !== pendente.evento) return;
    atualizando = null;
    var acao = pendente.acao;
    if (!acao.isConnected) return;
    if (document.querySelector("#carrinho [data-carrinho-alerta].aviso-erro")) return;
    fecharQuantidade(acao, true);
    mostrarFeito(acao.closest("li"), null, "Atualizado");
  });

  // "Confirmar": o HTMX 4 dispara o `htmx:after:swap` no botão que fez a requisição (ele fica na
  // página; a troca é no #carrinho). Sem erro na resposta, a quantidade fecha e vem o retorno; com
  // erro, ela fica aberta para corrigir (o motivo aparece no pedido).
  function avisarAdicionado(e) {
    var botao = e.target;
    if (!botao || !botao.matches || !botao.matches("#resultados [data-adicionar-confirmar]")) return;
    if (document.querySelector("#carrinho [data-carrinho-alerta].aviso-erro")) return;
    var item = botao.closest("li");
    var acao = botao.closest("[data-adicionar]");
    if (!acao) return mostrarFeito(item, botao, "Adicionado"); // um passo só
    fecharQuantidade(acao, true);
    mostrarFeito(item, null, "Adicionado");
  }
  document.addEventListener("htmx:after:swap", avisarAdicionado);

  document.addEventListener("htmx:before:swap", function () {
    var g = gaveta();
    reabrir = !!(g && g.open);
  });
  document.addEventListener("htmx:after:swap", atualizarPedido);
  document.addEventListener("htmx:after:swap", observarPasso);
  document.addEventListener("DOMContentLoaded", atualizarPedido);
  document.addEventListener("DOMContentLoaded", observarPasso);

  // Painel de resultados preso à busca (_materiais.html): abre ao focar a busca, ao digitar ou
  // ao trocar o filtro; fecha com Esc ou quando o foco ou o clique vão para fora da área. A
  // gaveta do pedido (<dialog>) não conta como "fora": ao fechá-la, o painel continua aberto.
  function painel() {
    return document.getElementById("resultados");
  }

  // O painel fica no fluxo, logo abaixo do campo de busca (o filtro de grupo fica acima dele).
  // `toggle` não sobe pela árvore: escuta na captura.
  document.addEventListener(
    "toggle",
    function (e) {
      if (!e.target.matches || !e.target.matches("[data-busca-filtro]")) return;
      // Os resultados cairiam por cima da lista de grupos: saem enquanto se escolhe e voltam com a
      // escolha (o `change` abaixo os abre de novo).
      if (e.target.open) fecharPainel(false);
      if (!e.target.open) return;
      // Abrir o filtro já abre a lista de grupos (o dropdown.js), para não pedir um segundo clique.
      var gatilho = e.target.querySelector(".dropdown-gatilho");
      if (gatilho && gatilho.getAttribute("aria-expanded") !== "true") gatilho.click();
      trazerAoTopo(e.target);
    },
    true
  );

  // Resumo do filtro de grupo (_materiais.html): mostra o escolhido, fica em destaque quando há
  // um, e o <details> se fecha depois da escolha.
  function resumirFiltro(select, recolher) {
    var filtro = select.closest("[data-busca-filtro]");
    if (!filtro) return;
    var opcao = select.options[select.selectedIndex];
    var texto = select.value && opcao ? opcao.textContent.trim().replace(/^Todo o grupo /, "") : "Todos";
    filtro.querySelector("[data-busca-filtro-valor]").textContent = texto;
    filtro.classList.toggle("busca-filtro-ativo", !!select.value);
    if (recolher) filtro.open = false;
  }

  // O painel que abre embaixo da busca (ou a lista de grupos embaixo do filtro) ficava cortado no pé
  // da tela (no celular, atrás da barra "Seu pedido"): em qualquer tela, a página rola para o
  // elemento ficar no topo, descontando a barra do almoxarifado quando ela é uma barra no topo (a
  // .app-lateral do celular; na tela larga ela é uma coluna). Só rola para baixo.
  // Com "reduzir movimento", o clean.css zera as transições: a rolagem também não anima.
  function rolagemSuave() {
    var campo = document.querySelector(".campo-entrada");
    return !campo || parseFloat(getComputedStyle(campo).transitionDuration) >= 0.05;
  }
  // `depois` roda quando a rolagem acaba (ou logo, se não precisou rolar).
  // Até onde a busca sobe: logo abaixo da barra do topo, quando ela fica presa ao rolar.
  function topoLivre() {
    var topo = 8;
    var barra = document.querySelector(".app-lateral");
    var noTopo = barra && barra.offsetWidth >= window.innerWidth / 2;
    if (noTopo && getComputedStyle(barra).position === "sticky") topo += barra.getBoundingClientRect().bottom;
    return topo;
  }
  function trazerAoTopo(el, depois) {
    if (!el) return;
    var topo = topoLivre();
    requestAnimationFrame(function () {
      var delta = el.getBoundingClientRect().top - topo;
      if (delta <= 0) return depois && depois();
      var suave = rolagemSuave();
      if (depois) {
        var feito = false;
        var uma = function () {
          if (feito) return;
          feito = true;
          window.removeEventListener("scrollend", uma);
          depois();
        };
        window.addEventListener("scrollend", uma);
        setTimeout(uma, suave ? 600 : 50); // navegador sem `scrollend`
      }
      window.scrollBy({ top: delta, behavior: suave ? "smooth" : "auto" });
    });
  }

  // O painel fica no fluxo da página (pedidos.css), logo abaixo da busca: o cartão e a página crescem
  // com ele, e o espaço reservado à barra "Seu pedido" (celular) vale para ele. A altura é a mesma em
  // qualquer tela (computador, tablet, celular): o cabeçalho e as LINHAS_VISIVEIS primeiras linhas,
  // medidas fechadas; o resto rola dentro do painel. Com mais que isso a página rola, não o painel.
  var LINHAS_VISIVEIS = 5;
  function alturaDoPainel() {
    var p = painel();
    if (!p || !p.classList.contains("aberto")) return;
    var area = p.closest("[data-busca-area]");
    var linhas = p.querySelectorAll("li.material");
    if (linhas.length <= LINHAS_VISIVEIS) return area.style.removeProperty("--busca-limite");
    // O topo da primeira linha de fora = o cabeçalho + as linhas visíveis (o painel é o offsetParent).
    var alto = linhas[LINHAS_VISIVEIS].offsetTop;
    // Uma linha aberta (quantidade à mostra) é mais alta que fechada: não conta o que ela acrescenta.
    var aberta = p.querySelector("[data-adicionar].aberto");
    var dela = aberta && aberta.closest("li");
    if (dela && Array.prototype.indexOf.call(linhas, dela) < LINHAS_VISIVEIS) {
      alto -= aberta.offsetHeight + (parseFloat(getComputedStyle(dela).rowGap) || 0);
    }
    area.style.setProperty("--busca-limite", Math.round(alto) + 2 + "px"); // + as bordas do painel
  }
  function soltarLimite() {
    var area = document.querySelector("[data-busca-area]");
    if (area) area.style.removeProperty("--busca-limite");
  }
  // A troca dos resultados e o tamanho da tela mudam a altura das linhas (o nome quebra mais ou menos).
  var ajusteAgendado = false;
  function agendarAjuste() {
    if (ajusteAgendado) return;
    ajusteAgendado = true;
    requestAnimationFrame(function () {
      ajusteAgendado = false;
      alturaDoPainel();
    });
  }
  window.addEventListener("resize", agendarAjuste);
  document.addEventListener("htmx:after:swap", agendarAjuste);

  function abrirPainel() {
    var p = painel();
    if (!p) return;
    // O abrir e fechar animados são os da base dos dropdowns (dropdown.js, `.painel-flutuante`).
    var estado = window.Dropdown.abrirPainel(p);
    // Reaberto no meio da saída: fica aberto, sem repetir a entrada.
    if (estado === "reaberto") {
      var campo = document.getElementById("busca-q");
      if (campo) campo.setAttribute("aria-expanded", "true");
      return;
    }
    if (estado === "ja") return;
    var busca = document.getElementById("busca-q");
    if (busca) busca.setAttribute("aria-expanded", "true");
    alturaDoPainel();
    trazerAoTopo(document.querySelector(".busca-principal"));
  }

  function fecharPainel(devolverFoco) {
    var p = painel();
    if (!p || !window.Dropdown.fecharPainel(p, soltarLimite)) return;
    var busca = document.getElementById("busca-q");
    esconderDica();
    if (!busca) return;
    busca.setAttribute("aria-expanded", "false");
    if (aoToque()) busca.setAttribute("inputmode", "none");
    if (devolverFoco) busca.focus();
  }

  function dentroDaBusca(alvo) {
    return !!(alvo && alvo.closest && (alvo.closest("[data-busca-area]") || alvo.closest("dialog")));
  }

  // Celular e tablet: o primeiro toque no campo abre a lista sem o teclado (`inputmode="none"`), que
  // cobriria os resultados, e uma dica pede o segundo toque, que libera o teclado para digitar e
  // filtrar. Com a lista fechada o campo volta a ficar sem teclado. Mouse e teclado físico não mudam.
  var sobDica = null;
  function aoToque() {
    return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
  }
  function dicaBusca() {
    return document.querySelector("[data-busca-dica]");
  }
  function esconderDica() {
    clearTimeout(sobDica);
    var dica = dicaBusca();
    if (dica) dica.hidden = true;
  }
  function mostrarDica() {
    var dica = dicaBusca();
    if (!dica) return;
    dica.hidden = false;
    clearTimeout(sobDica);
    sobDica = setTimeout(esconderDica, 6000);
  }
  var liberarNoClique = false;
  document.addEventListener(
    "pointerdown",
    function (e) {
      var campo = e.target;
      if (campo.id !== "busca-q" || !aoToque()) return;
      var p = painel();
      var aberto = p && window.Dropdown.painelAberto(p);
      if (aberto && campo.getAttribute("inputmode") === "none") {
        // Segundo toque: o teclado só sobe quando o campo ganha o foco de novo, dentro do clique.
        campo.removeAttribute("inputmode");
        liberarNoClique = true;
        esconderDica();
      } else if (!aberto) {
        campo.setAttribute("inputmode", "none");
        abrirPainel();
        mostrarDica();
      }
    },
    true
  );
  document.addEventListener("click", function (e) {
    if (!liberarNoClique || e.target.id !== "busca-q") return;
    liberarNoClique = false;
    e.target.blur();
    e.target.focus();
  });

  document.addEventListener("focusin", function (e) {
    if (e.target.id === "busca-q") return abrirPainel();
    if (!dentroDaBusca(e.target) && !window.Dropdown.gestoEmAndamento()) fecharPainel(false);
  });
  // Toque fora fecha; arrastar a página por trás do painel, não (`Dropdown.aoTocarFora`).
  window.Dropdown.aoTocarFora(function (alvo) {
    if (!dentroDaBusca(alvo)) fecharPainel(false);
  });
  document.addEventListener("input", function (e) {
    if (e.target.id !== "busca-q") return;
    esconderDica();
    abrirPainel();
  });
  // "Limpar" volta a "Todos os grupos" pelo mesmo `change` da escolha (HTMX, resumo e resultados).
  document.addEventListener("click", function (e) {
    var limpar = e.target.closest && e.target.closest("[data-busca-filtro-limpar]");
    var select = limpar && document.getElementById("busca-filtro");
    if (!select) return;
    select.value = "";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    var resumo = document.querySelector("[data-busca-filtro] > summary");
    if (resumo) resumo.focus();
  });
  document.addEventListener("change", function (e) {
    if (e.target.id !== "busca-filtro") return;
    resumirFiltro(e.target, true);
    abrirPainel();
  });
  // O navegador pode devolver o filtro escolhido ao voltar para a página.
  document.addEventListener("DOMContentLoaded", function () {
    var select = document.getElementById("busca-filtro");
    if (select) resumirFiltro(select, false);
  });
  document.addEventListener("keydown", function (e) {
    var alvo = e.target;
    if (!alvo || !alvo.closest || !alvo.closest("[data-busca-area]")) return;
    if (e.key === "Escape" && !document.querySelector("dialog[open]")) {
      fecharPainel(true);
    } else if (e.key === "ArrowDown" && alvo.id === "busca-q") {
      // ↓ na busca leva ao primeiro material que pode ser adicionado.
      abrirPainel();
      var primeiro = null;
      (painel() ? painel().querySelectorAll("[data-adicionar-abrir], .quantidade-campo") : []).forEach(
        function (el) {
          if (!primeiro && el.offsetParent !== null) primeiro = el;
        }
      );
      if (primeiro) {
        e.preventDefault();
        primeiro.focus();
      }
    }
  });

  // "Não lançar" em dois passos (Automações, aba Lançamento no SCPI): o <details> abre a confirmação, que funciona
  // sem JavaScript (desistir é fechar pelo próprio <summary>). Com JavaScript, o "Desistir" fecha
  // e devolve o foco ao <summary>; ele aparece também nas travas trazidas pela recarga do HTMX.
  function mostrarDesistir() {
    document.querySelectorAll("[data-desistir]").forEach(function (botao) {
      botao.hidden = false;
    });
  }
  document.addEventListener("DOMContentLoaded", mostrarDesistir);
  document.addEventListener("htmx:after:swap", mostrarDesistir);
  document.addEventListener("click", function (e) {
    var botao = e.target.closest && e.target.closest("[data-desistir]");
    var detalhes = botao && botao.closest("details");
    if (!detalhes) return;
    detalhes.open = false;
    var resumo = detalhes.querySelector("summary");
    if (resumo) resumo.focus();
  });

  // Modo de edição do atendimento e da saída avulsa (`form[data-editando]`). As quantidades gravadas
  // abrem confirmadas; cada campo diferente do que estava gravado ganha o destaque "alterado" e o
  // rodapé conta as alterações (por campo da saída e por material). Sair da página com alteração
  // pede confirmação, e o "Descartar" também. O resumo de um salvar recusado se copia com um botão.
  function formEdicao() {
    return document.querySelector("form[data-editando]");
  }

  // Só o que a edição grava conta como alteração: os campos da saída e os materiais. A busca, o
  // filtro de grupo e os campos de quantidade dos resultados não.
  var CAMPOS_DA_SAIDA = ["data", "recebedor", "centro_custo", "tipo", "placa", "obs", "nao_lancar"];

  // A unidade de alteração de um campo: o próprio campo da saída, ou o material dele (quantidade,
  // troca, presença no carrinho). `null` para o que não é dado da saída.
  function unidadeDoCampo(campo) {
    var nome = campo.name;
    if (!nome || campo.disabled) return null;
    if (CAMPOS_DA_SAIDA.indexOf(nome) !== -1) return nome;
    if (nome === "item_qtd") {
      var linha = campo.closest(".carrinho-linha[data-codigo]");
      return linha ? "material:" + linha.getAttribute("data-codigo") : null;
    }
    if (nome === "adicionado") return "material:" + campo.value;
    if (nome.indexOf("entregue-") === 0) return "material:" + nome.slice("entregue-".length);
    if (nome.indexOf("no-lugar-de-") === 0) return "material:" + nome.slice("no-lugar-de-".length);
    return null;
  }

  function valorDoCampo(campo) {
    if (campo.type === "checkbox") return campo.checked ? "1" : "";
    if (campo.name === "adicionado") return "+";
    if (campo.name.indexOf("no-lugar-de-") === 0) return ">" + campo.value;
    return campo.value;
  }

  // Campos do formulário (também os de fora dele, ligados por `form=`), agrupados por unidade.
  // O retrato é por valor, não por elemento: o HTMX troca o carrinho e os acrescentados por
  // elementos novos, e o mesmo conteúdo continua sem alteração.
  function unidadesDaEdicao(form) {
    var unidades = {};
    Array.prototype.forEach.call(form.elements, function (campo) {
      var chave = unidadeDoCampo(campo);
      if (chave === null) return;
      unidades[chave] = (unidades[chave] === undefined ? "" : unidades[chave] + "|") + valorDoCampo(campo);
    });
    return unidades;
  }

  var unidadesIniciais = null;
  var descartando = false;

  function contarAlteracoes(form) {
    var atuais = unidadesDaEdicao(form);
    var chaves = {};
    Object.keys(unidadesIniciais).concat(Object.keys(atuais)).forEach(function (k) { chaves[k] = true; });
    return Object.keys(chaves).filter(function (k) { return unidadesIniciais[k] !== atuais[k]; }).length;
  }

  // Valor de abertura de cada campo de quantidade, pelo nome (o HTMX troca os elementos, o nome
  // fica): é o "era" da nota do material.
  var valoresIniciais = {};

  function chaveDoValor(campo) {
    var linha = campo.name === "item_qtd" && campo.closest(".carrinho-linha[data-codigo]");
    return linha ? "item_qtd:" + linha.getAttribute("data-codigo") : campo.name;
  }

  // Onde a nota vai, sem empurrar o campo: no material, embaixo do nome (como o "Trocado por …"),
  // com o valor de antes; nos dados da saída, na linha do rótulo.
  function notaDoCampo(campo, caixa) {
    if (caixa.classList.contains("campo")) {
      return { lugar: caixa.querySelector(".campo-rotulo") || caixa, classe: "campo-dica-alterado", texto: "alterado" };
    }
    var antes = valoresIniciais[chaveDoValor(campo)];
    var unidade = caixa.querySelector(".entrega-un");
    var texto = antes === undefined
      ? "Incluído nesta edição"
      : "Alterado: era " + antes + (unidade ? " " + unidade.textContent.trim() : "");
    if (caixa.classList.contains("entrega")) {
      var linha = caixa.closest("tr");
      return { lugar: linha ? linha.cells[0] : caixa, classe: "recibo-nota campo-dica-alterado", texto: texto };
    }
    return { lugar: caixa.querySelector(".material-dados") || caixa, classe: "campo-dica campo-dica-alterado", texto: texto };
  }

  // O destaque fica no invólucro do campo (`.campo`, `.entrega`, linha do carrinho), e a nota com
  // o texto, para não depender só da cor.
  function destacarCampo(campo, atuais) {
    var chave = unidadeDoCampo(campo);
    var caixa = campo.closest(".campo, .entrega, .carrinho-linha");
    if (chave === null || !caixa) return;
    var mudou = unidadesIniciais[chave] !== atuais[chave];
    caixa.classList.toggle("campo-alterado", mudou);
    var nota = notaDoCampo(campo, caixa);
    var existente = nota.lugar.querySelector(":scope > .campo-dica-alterado");
    if (!mudou) {
      if (existente) existente.remove();
      return;
    }
    if (!existente) {
      existente = document.createElement("span");
      nota.lugar.appendChild(existente);
    }
    existente.className = nota.classe;
    existente.textContent = nota.texto;
  }

  function atualizarEdicao() {
    var form = formEdicao();
    if (!form || !unidadesIniciais) return;
    var atuais = unidadesDaEdicao(form);
    Array.prototype.forEach.call(form.elements, function (campo) {
      if (campo.type === "hidden") return;
      destacarCampo(campo, atuais);
    });
    var n = contarAlteracoes(form);
    var contagem = document.querySelector("[data-contagem-alteracoes]");
    if (contagem) contagem.textContent = n === 0 ? "" : n === 1 ? "1 alteração" : n + " alterações";
  }

  function iniciarEdicao() {
    var copiar = document.querySelector("[data-copiar-resumo]");
    if (copiar && navigator.clipboard) copiar.hidden = false;
    var form = formEdicao();
    if (!form) return;
    // Quantidades gravadas já valem: abrem confirmadas (as trocadas o `iniciarTrocas` confirmou).
    document.querySelectorAll(".entrega[data-pode-confirmar]:not([data-confirmado])").forEach(function (bloco) {
      var estado = bloco.getAttribute("data-estado");
      if (estado === "invalido" || estado === "acima") return;
      if (estado === "zero" && bloco.closest("tr[data-adicionado]")) return;
      confirmarEntrega(bloco);
    });
    unidadesIniciais = unidadesDaEdicao(form);
    Array.prototype.forEach.call(form.elements, function (campo) {
      if (unidadeDoCampo(campo) !== null && campo.type !== "hidden") valoresIniciais[chaveDoValor(campo)] = campo.value;
    });
    atualizarEdicao();
  }
  document.addEventListener("DOMContentLoaded", iniciarEdicao);
  document.addEventListener("input", atualizarEdicao);
  document.addEventListener("change", atualizarEdicao);
  document.addEventListener("htmx:after:swap", function () { setTimeout(atualizarEdicao, 0); });
  // A faixa voltou encerrada (o lote entrou em lançamento): nada mais se salva nesta página.
  document.addEventListener("htmx:after:swap", function () {
    var form = formEdicao();
    if (!form || !document.querySelector("[data-edicao-encerrada]")) return;
    document.querySelectorAll('button[type="submit"], [data-carrinho-enviar]').forEach(function (botao) {
      if (botao.form !== form && !botao.hasAttribute("data-carrinho-enviar")) return;
      botao.disabled = true;
    });
    descartando = true;
  });
  // Troca, acréscimo e o − e o + mudam os campos por código, sem `input`.
  document.addEventListener("click", function () { setTimeout(atualizarEdicao, 0); });

  document.addEventListener("submit", function (e) {
    if (e.target.matches && e.target.matches("form[data-editando]")) descartando = true;
  });
  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest("[data-descartar-edicao], .link-voltar");
    var form = formEdicao();
    if (!link || !form || !unidadesIniciais || contarAlteracoes(form) === 0) return;
    if (!window.confirm("Descartar as alterações?")) {
      e.preventDefault();
      return;
    }
    descartando = true;
  });
  window.addEventListener("beforeunload", function (e) {
    var form = formEdicao();
    if (descartando || !form || !unidadesIniciais || contarAlteracoes(form) === 0) return;
    e.preventDefault();
    e.returnValue = "";
  });

  document.addEventListener("click", function (e) {
    var botao = e.target.closest && e.target.closest("[data-copiar-resumo]");
    if (!botao) return;
    var lista = document.querySelector("[data-resumo-alteracoes]");
    var texto = Array.prototype.map.call(lista.querySelectorAll("li"), function (li) {
      return "- " + li.textContent.trim();
    }).join("\n");
    navigator.clipboard.writeText(texto).then(function () {
      var rotulo = botao.querySelector("span");
      var antes = rotulo.textContent;
      rotulo.textContent = "Copiado";
      setTimeout(function () { rotulo.textContent = antes; }, 2000);
    });
  });

  // Folha (spec 006, contracts/folha.md): a lista de peças preenchida como o papel, num <dialog>
  // dentro do <form>. O botão `data-folha-abrir` pede ao servidor o conteúdo já com as quantidades
  // do pedido; aqui o diálogo abre, recebe o foco e fecha. "Pôr no pedido" (`data-folha-aplicar`)
  // manda a folha inteira: sem erro, o servidor devolve o carrinho e o evento `folha-aplicada`; com
  // erro, devolve a própria folha (HX-Retarget) e o foco vai para o resumo.
  function folha() {
    return document.getElementById("folha");
  }

  function botaoDaFolha() {
    return document.querySelector("[data-folha-abrir]");
  }

  function fecharFolha() {
    var d = folha();
    if (d && d.open) d.close();
  }

  // Cada conteúdo novo do servidor chega marcado (`data-folha-nova`) e é mostrado uma vez: as outras
  // trocas da página (o carrinho, a busca) não reabrem a folha.
  document.addEventListener("htmx:after:swap", function () {
    var d = folha();
    var nova = d && d.querySelector("[data-folha-nova]");
    if (!nova) return;
    nova.removeAttribute("data-folha-nova");
    if (!d.open && d.showModal) d.showModal();
    var botao = botaoDaFolha();
    if (botao) botao.setAttribute("aria-expanded", "true");
    var resumo = nova.querySelector("[data-folha-resumo]");
    var primeiro = nova.querySelector(".folha-qtd[aria-invalid='true']") || nova.querySelector(".folha-qtd");
    if (resumo) resumo.focus();
    else if (primeiro) primeiro.focus();
  });

  document.addEventListener("folha-aplicada", function () {
    fecharFolha();
    var anuncio = document.querySelector("[data-anuncio-adicionado]");
    var n = document.querySelectorAll('#carrinho input[name="item_codigo"]').length;
    if (anuncio) {
      anuncio.textContent =
        "Lista posta no pedido: " + n + (n === 1 ? " material." : " materiais.");
    }
  });

  // Fechar (botão, Esc ou fundo) não muda o pedido; o foco volta ao botão que abriu.
  document.addEventListener(
    "close",
    function (e) {
      if (e.target.id !== "folha") return;
      var botao = botaoDaFolha();
      if (!botao) return;
      botao.setAttribute("aria-expanded", "false");
      botao.focus();
    },
    true
  );

  document.addEventListener("click", function (e) {
    var alvo = e.target;
    if (!alvo || !alvo.closest) return;
    if (alvo.closest("[data-folha-fechar]")) return fecharFolha();
    var d = folha();
    if (d && d.open && alvo === d) {
      var r = d.getBoundingClientRect();
      if (e.clientY < r.top || e.clientY > r.bottom || e.clientX < r.left || e.clientX > r.right) {
        fecharFolha();
      }
    }
  });

  // Enter numa linha da folha põe a folha no pedido; nunca envia o pedido inteiro.
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || !e.target.matches || !e.target.matches(".folha-qtd")) return;
    e.preventDefault();
    var aplicar = document.querySelector("[data-folha-aplicar]");
    if (aplicar) aplicar.click();
  });

  // Falha de rede ou do servidor ao abrir ou aplicar a folha: o que foi digitado fica, e o aviso
  // aparece dentro dela (ou no topo do formulário, se ela nem abriu).
  function avisarFalhaDaFolha(e) {
    var origem = e.target;
    if (!origem || !origem.closest) return;
    if (!origem.closest("[data-folha-aplicar]") && !origem.closest("[data-folha-abrir]")) return;
    var caixa = document.querySelector("[data-folha-falha]");
    var d = folha();
    if (!caixa || !d || !d.open) {
      caixa = document.querySelector("[data-formulario-pedido] [data-erro-envio]");
    }
    if (!caixa) return;
    caixa.className = "aviso aviso-erro";
    caixa.textContent =
      "Não foi possível pôr a lista no pedido. O que foi digitado foi mantido; tente de novo.";
  }
  document.addEventListener("htmx:error", avisarFalhaDaFolha);
  document.addEventListener("htmx:response:error", avisarFalhaDaFolha);
})();
