/*
 * Filtros recolhíveis — o formulário `form[data-filtros]` (painel de pedidos). Carregado com
 * `defer` no <head>.
 *
 * Melhoria progressiva: sem JavaScript o painel fica aberto e o botão "Filtrar" envia. Com ele,
 * o botão "Filtros" abre e fecha o painel (o estado fica guardado no navegador), a contagem
 * mostra quantos filtros do painel estão ativos e, com o painel fechado, cada filtro ativo vira
 * um chip que o remove. Remover um chip troca o valor do campo e dispara `change`, que o HTMX
 * do formulário já escuta (e o dropdown.js também, para atualizar o gatilho).
 *
 * O `form[data-filtros-auto]` (catálogo: Formulários e Curva ABC) é mais simples: sem painel, só
 * envia o formulário quando um campo muda.
 *
 * Os eventos são delegados no `document`: ao restaurar o histórico, o HTMX troca o <body> e os
 * elementos são outros.
 */
(function () {
  "use strict";

  var CHAVE = "filtros-painel-aberto";

  function lerAberto() {
    try {
      return localStorage.getItem(CHAVE) === "1";
    } catch (e) {
      return false;
    }
  }

  function gravarAberto(aberto) {
    try {
      localStorage.setItem(CHAVE, aberto ? "1" : "0");
    } catch (e) {
      /* sem armazenamento: o painel só não lembra o estado */
    }
  }

  function data(valor) {
    var p = /^(\d{4})-(\d{2})-(\d{2})$/.exec(valor || "");
    return p ? p[3] + "/" + p[2] + "/" + p[1] : valor;
  }

  function rotulo(form, campo) {
    var r = campo.id && form.querySelector('label[for="' + campo.id + '"]');
    return r ? r.textContent.trim() : campo.name;
  }

  // Os filtros ativos do painel (a busca fica de fora: ela já aparece no próprio campo).
  function ativos(form) {
    var lista = [];
    var painel = form.querySelector("[data-filtros-painel]");
    painel.querySelectorAll("select").forEach(function (s) {
      if (!s.value) return;
      lista.push({
        texto: rotulo(form, s) + ": " + s.options[s.selectedIndex].textContent.trim(),
        campos: [s],
      });
    });
    var de = form.elements.de;
    var ate = form.elements.ate;
    if (de && ate && (de.value || ate.value)) {
      var texto;
      if (de.value && ate.value) texto = data(de.value) + " a " + data(ate.value);
      else if (de.value) texto = "a partir de " + data(de.value);
      else texto = "até " + data(ate.value);
      lista.push({ texto: "Período: " + texto, campos: [de, ate] });
    }
    return lista;
  }

  function icone(tracos) {
    return (
      '<svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ' +
      'focusable="false">' + tracos + "</svg>"
    );
  }
  var FECHAR = icone('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>');

  function atualizar(form) {
    var painel = form.querySelector("[data-filtros-painel]");
    var botao = form.querySelector("[data-filtros-alternar]");
    var contagem = form.querySelector("[data-filtros-contagem]");
    var chips = form.querySelector("[data-filtros-chips]");
    var limpar = form.querySelector("[data-filtros-limpar]");
    var aberto = !painel.hidden;
    var lista = ativos(form);

    botao.setAttribute("aria-expanded", aberto ? "true" : "false");
    contagem.hidden = !lista.length;
    contagem.textContent = lista.length;
    botao.setAttribute(
      "aria-label",
      "Filtros" + (lista.length ? " (" + lista.length + (lista.length > 1 ? " ativos)" : " ativo)") : "")
    );
    limpar.hidden = !lista.length && !(form.elements.q && form.elements.q.value.trim());

    // Redesenhar apaga o chip com o foco: ele volta para o chip na mesma posição, ou para o
    // botão "Filtros" se não sobrou nenhum.
    var focado = chips.contains(document.activeElement)
      ? Number(document.activeElement.getAttribute("data-filtro-remover"))
      : -1;
    chips.textContent = "";
    chips.hidden = aberto || !lista.length;
    if (chips.hidden) {
      if (focado >= 0) botao.focus();
      return;
    }
    lista.forEach(function (item, i) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.className = "filtros-chip";
      b.setAttribute("data-filtro-remover", i);
      b.setAttribute("aria-label", "Remover filtro " + item.texto);
      var t = document.createElement("span");
      t.textContent = item.texto;
      b.appendChild(t);
      b.insertAdjacentHTML("beforeend", FECHAR);
      li.appendChild(b);
      chips.appendChild(li);
    });
    if (focado >= 0) chips.querySelectorAll("button")[Math.min(focado, lista.length - 1)].focus();
  }

  function iniciar() {
    document.querySelectorAll("form[data-filtros]").forEach(function (form) {
      form.querySelector("[data-filtros-painel]").hidden = !lerAberto();
      atualizar(form);
    });
  }

  document.addEventListener("click", function (e) {
    var alternar = e.target.closest("[data-filtros-alternar]");
    if (alternar) {
      var form = alternar.closest("form[data-filtros]");
      var painel = form.querySelector("[data-filtros-painel]");
      painel.hidden = !painel.hidden;
      gravarAberto(!painel.hidden);
      atualizar(form);
      return;
    }
    var remover = e.target.closest("[data-filtro-remover]");
    if (remover) {
      var f = remover.closest("form[data-filtros]");
      var item = ativos(f)[Number(remover.getAttribute("data-filtro-remover"))];
      if (!item) return;
      item.campos.forEach(function (c) {
        c.value = "";
      });
      // Um único `change`, para sair um único pedido do HTMX; o `atualizar` que ele provoca
      // redesenha os chips e cuida do foco.
      remover.focus();
      item.campos[item.campos.length - 1].dispatchEvent(new Event("change", { bubbles: true }));
    }
  });

  // `form[data-filtros-auto]` (filtros em página inteira, sem HTMX): escolher uma opção ou sair do
  // campo de busca com o texto alterado já envia o formulário, sem precisar do Enter. O botão
  // "Filtrar" só aparece sem JavaScript. O `change` do dropdown.js (que troca os `select`) também
  // chega aqui. Enquanto o texto é digitado nada é enviado: a página recarregaria e o foco se perderia.
  document.addEventListener("change", function (e) {
    var form = e.target.closest && e.target.closest("form[data-filtros-auto]");
    if (form && form.requestSubmit) form.requestSubmit();
  });

  ["change", "input"].forEach(function (tipo) {
    document.addEventListener(tipo, function (e) {
      var form = e.target.closest && e.target.closest("form[data-filtros]");
      if (form) atualizar(form);
    });
  });

  document.addEventListener("DOMContentLoaded", iniciar);
  document.addEventListener("htmx:after:swap", iniciar);
})();
