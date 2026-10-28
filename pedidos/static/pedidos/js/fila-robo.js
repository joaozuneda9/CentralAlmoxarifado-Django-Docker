/*
 * Fila do robô na aba Lançamento no SCPI: marcar as requisições a processar. Marcar a linha,
 * "marcar todas" no cabeçalho, contagem no `aria-live` e botões só com seleção. Com o lançamento
 * real liberado, o botão "Lançar no SCPI" abre antes a confirmação (#dialogo-lancar, dialogo.js).
 * Carregado no <head> com defer. Sem JavaScript, as caixas e os botões enviam o formulário e o
 * servidor recusa o envio sem requisição marcada ou com uma que já saiu da fila.
 */
(function () {
  "use strict";

  function plural(n, um, varios) {
    return n === 1 ? um : varios;
  }

  function sincronizar(form) {
    var caixas = Array.prototype.slice.call(form.querySelectorAll('tbody input[name="lotes"]'));
    var marcadas = caixas.filter(function (c) { return c.checked; });
    var n = marcadas.length;
    caixas.forEach(function (c) {
      var linha = c.closest("tr");
      if (linha) linha.classList.toggle("marcada", c.checked);
    });
    var todas = form.querySelector("[data-fila-todas]");
    if (todas) {
      todas.checked = caixas.length > 0 && n === caixas.length;
      todas.indeterminate = n > 0 && n < caixas.length;
    }
    var contagem = form.querySelector("[data-fila-contagem]");
    if (contagem && caixas.length) {
      var texto = n
        ? n + " de " + caixas.length + " " + plural(n, "requisição selecionada", "requisições selecionadas")
        : "Nenhuma requisição selecionada";
      var apoio = n ? "" : "Marque na lista o que o robô deve processar.";
      contagem.textContent = texto;
      if (apoio) {
        var small = document.createElement("small");
        small.textContent = apoio;
        contagem.appendChild(small);
      }
    }
    var sem = !caixas.length || caixas[0].disabled;
    form.querySelectorAll("[data-requer-selecao]").forEach(function (b) {
      b.disabled = sem || n === 0;
    });
    var confirmacao = document.querySelector("[data-fila-confirmacao]");
    if (confirmacao) {
      confirmacao.textContent = n
        ? plural(n, "A requisição ", "As requisições ") +
          marcadas.map(function (c) { return c.value; }).join(", ") +
          plural(n, " será lançada", " serão lançadas") +
          " de verdade no SCPI. Não dá para desfazer por aqui."
        : "";
    }
  }

  // Até 1286px a barra lateral vira um cabeçalho fixo (layouts.css) que cobriria a barra da fila
  // ao rolar: a barra da fila gruda logo abaixo dele (`--fila-topo`, pedidos.css).
  var CABECALHO_FIXO = window.matchMedia("(max-width: 1286px)");

  function ajustarTopo() {
    var cabecalho = document.querySelector(".app-lateral");
    var altura = cabecalho && CABECALHO_FIXO.matches ? cabecalho.getBoundingClientRect().height : 0;
    document.documentElement.style.setProperty("--fila-topo", altura + "px");
  }

  function preparar() {
    document.querySelectorAll("form[data-fila-robo]").forEach(sincronizar);
    ajustarTopo();
  }

  window.addEventListener("resize", ajustarTopo);
  if (window.ResizeObserver) {
    var observado = document.querySelector(".app-lateral");
    if (observado) new ResizeObserver(ajustarTopo).observe(observado);
  }

  document.addEventListener("DOMContentLoaded", preparar);
  document.addEventListener("htmx:after:swap", preparar);

  document.addEventListener("change", function (e) {
    var form = e.target.closest && e.target.closest("form[data-fila-robo]");
    if (!form) return;
    if (e.target.matches("[data-fila-todas]")) {
      form.querySelectorAll('tbody input[name="lotes"]:not(:disabled)').forEach(function (c) {
        c.checked = e.target.checked;
      });
    }
    sincronizar(form);
  });

  // Clicar na linha alterna a caixa (o número do pedido segue sendo um link).
  document.addEventListener("click", function (e) {
    var alvo = e.target;
    if (!alvo.closest) return;
    var linha = alvo.closest("tr[data-fila-linha]");
    if (linha && !alvo.closest("a, label, input, button")) {
      var caixa = linha.querySelector('input[name="lotes"]');
      if (caixa && !caixa.disabled) {
        caixa.checked = !caixa.checked;
        caixa.dispatchEvent(new Event("change", { bubbles: true }));
      }
      return;
    }
    // Lançamento real: confirma antes de enviar.
    var lancar = alvo.closest("[data-confirmar-lancamento]");
    if (lancar && !lancar.disabled) {
      var dialogo = document.getElementById("dialogo-lancar");
      if (dialogo && typeof dialogo.showModal === "function") {
        e.preventDefault();
        if (!dialogo.open) dialogo.showModal();
      }
    }
  });
})();
