/*
 * Abas (componente comum, `[data-abas]`): troca o painel, guarda a aba na URL (`?aba=`) e anda com
 * as setas, Home e End (padrão WAI-ARIA). Quando as abas não cabem, marca de que lado a lista
 * continua (`data-mais-inicio`/`data-mais-fim`). Ao abrir uma aba, dispara `abas:ativada` no painel. Carregado no <head> com defer, em todas as páginas.
 * Sem JavaScript, todos os painéis ficam à vista, empilhados.
 */
(function () {
  "use strict";

  function abasDe(raiz) {
    return Array.prototype.slice.call(raiz.querySelectorAll("[role=tab]"));
  }

  // No celular a lista rola de lado: a aba ativa não pode ficar cortada na borda.
  function mostrar(aba) {
    var lista = aba.parentElement;
    var folga = 16;
    if (aba.offsetLeft - folga < lista.scrollLeft) {
      lista.scrollLeft = aba.offsetLeft - folga;
    } else if (aba.offsetLeft + aba.offsetWidth + folga > lista.scrollLeft + lista.clientWidth) {
      lista.scrollLeft = aba.offsetLeft + aba.offsetWidth + folga - lista.clientWidth;
    }
  }

  function ativar(raiz, chave, focar) {
    abasDe(raiz).forEach(function (aba) {
      var ativa = aba.getAttribute("data-aba") === chave;
      aba.classList.toggle("aba-ativa", ativa);
      aba.setAttribute("aria-selected", ativa ? "true" : "false");
      aba.setAttribute("tabindex", ativa ? "0" : "-1");
      if (ativa) mostrar(aba);
      if (ativa && focar) aba.focus();
    });
    var ativado = null;
    raiz.querySelectorAll("[role=tabpanel]").forEach(function (painel) {
      var ativo = painel.id === "painel-" + chave;
      painel.classList.toggle("aba-painel-ativo", ativo);
      if (ativo) ativado = painel;
    });
    // Avisa o painel que abriu (`abas:ativada`, sobe pelo DOM): um painel que veio vazio se carrega
    // por aí (`hx-trigger="abas:ativada once"`).
    if (ativado) ativado.dispatchEvent(new CustomEvent("abas:ativada", { bubbles: true }));
    // A aba fica na URL: recarregar a página (ou voltar de um envio com erro) mantém a aba.
    try {
      // (a página pode ter vindo de um envio com erro, em outra URL; a aba vai na da própria página)
      var url = new URL(raiz.getAttribute("data-url") || window.location.pathname, window.location.href);
      url.searchParams.set("aba", chave);
      window.history.replaceState(null, "", url);
    } catch (e) {
      /* histórico indisponível: a aba só não fica na URL */
    }
  }

  document.addEventListener("click", function (e) {
    var aba = e.target.closest && e.target.closest("[role=tab][data-aba]");
    var raiz = aba && aba.closest("[data-abas]");
    if (raiz) ativar(raiz, aba.getAttribute("data-aba"), false);
  });

  // Link que leva a outra aba da mesma página (`data-abrir-aba="<chave>"`, com `href="?aba=<chave>"`
  // para quem está sem JavaScript): troca a aba, sobe até ela e põe o foco nela.
  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest("[data-abrir-aba]");
    var raiz = link && link.closest("[data-abas]");
    if (!raiz) return;
    var chave = link.getAttribute("data-abrir-aba");
    var aba = raiz.querySelector('[role=tab][data-aba="' + chave + '"]');
    if (!aba) return;
    e.preventDefault();
    ativar(raiz, chave, true);
    raiz.scrollIntoView({ block: "start" });
  });

  document.addEventListener("keydown", function (e) {
    var aba = e.target.closest && e.target.closest("[role=tab][data-aba]");
    var raiz = aba && aba.closest("[data-abas]");
    if (!raiz) return;
    var todas = abasDe(raiz);
    var i = todas.indexOf(aba);
    var destino = null;
    if (e.key === "ArrowRight") destino = todas[(i + 1) % todas.length];
    else if (e.key === "ArrowLeft") destino = todas[(i - 1 + todas.length) % todas.length];
    else if (e.key === "Home") destino = todas[0];
    else if (e.key === "End") destino = todas[todas.length - 1];
    if (!destino) return;
    e.preventDefault();
    ativar(raiz, destino.getAttribute("data-aba"), true);
  });

  // Lista que não cabe: marca de que lado ainda há abas, para o CSS esmaecer aquela borda.
  function marcarRolagem(lista) {
    var folga = 2;
    lista.toggleAttribute("data-mais-inicio", lista.scrollLeft > folga);
    lista.toggleAttribute("data-mais-fim", lista.scrollLeft + lista.clientWidth < lista.scrollWidth - folga);
  }

  function marcarTodas() {
    document.querySelectorAll("[data-abas] [role=tablist]").forEach(marcarRolagem);
  }

  // A rolagem não sobe pelo DOM: escuta na captura, para valer também nas listas trocadas pelo HTMX.
  document.addEventListener(
    "scroll",
    function (e) {
      if (e.target.matches && e.target.matches("[data-abas] [role=tablist]")) marcarRolagem(e.target);
    },
    { capture: true, passive: true }
  );
  window.addEventListener("resize", marcarTodas);

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-abas] .aba-ativa").forEach(mostrar);
    marcarTodas();
  });
})();
