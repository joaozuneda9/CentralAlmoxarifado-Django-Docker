/*
 * Mantém a rolagem da página ao enviar um formulário que volta para a mesma página
 * (`form[data-manter-rolagem]` e os filtros `form[data-filtros-auto]`): a lista recarrega e a
 * tela continua onde estava, em vez de voltar ao topo. Carregado no <head> com defer.
 *
 * O `a[data-rolar-ate]` faz o contrário: abre a página no topo e a desliza até um elemento (os
 * atalhos "Atender" e "Imprimir" do painel).
 *
 * A posição vai para o `sessionStorage` no envio e é usada uma única vez, só se a página que
 * carrega é a mesma (mesmo caminho; o filtro e a página podem mudar). Sem JavaScript, ou sem
 * `sessionStorage`, o comportamento é o de sempre: a página abre no topo.
 */
(function () {
  "use strict";

  var CHAVE = "rolagem-ao-voltar";

  function guardar() {
    try {
      sessionStorage.setItem(
        CHAVE,
        JSON.stringify({ caminho: window.location.pathname, y: window.scrollY })
      );
    } catch (e) {
      /* sem armazenamento, a página só abre no topo */
    }
  }

  function lerEApagar() {
    try {
      var texto = sessionStorage.getItem(CHAVE);
      sessionStorage.removeItem(CHAVE);
      var dado = texto && JSON.parse(texto);
      return dado && dado.caminho === window.location.pathname ? dado.y : null;
    } catch (e) {
      return null;
    }
  }

  document.addEventListener("submit", function (e) {
    if (e.target.matches && e.target.matches("form[data-manter-rolagem], form[data-filtros-auto]")) {
      guardar();
    }
  });

  // `a[data-rolar-ate="id"]`: o link abre a página no topo e ela desliza até o elemento `id`, em
  // vez de saltar para a âncora. Sem JavaScript vale o `#id` do próprio `href`. Quem prefere menos
  // movimento recebe o salto de sempre.
  var ALVO = "rolagem-ate-o-alvo";

  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest("a[data-rolar-ate]");
    if (!link || e.defaultPrevented || e.button !== 0) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var destino = new URL(link.href, window.location.href);
    try {
      sessionStorage.setItem(
        ALVO,
        JSON.stringify({ caminho: destino.pathname, id: link.getAttribute("data-rolar-ate") })
      );
    } catch (erro) {
      return; // sem armazenamento, o link segue com a âncora
    }
    e.preventDefault();
    destino.hash = "";
    window.location.assign(destino.href);
  });

  function deslizarAteOAlvo() {
    var id = null;
    try {
      var dado = JSON.parse(sessionStorage.getItem(ALVO) || "null");
      sessionStorage.removeItem(ALVO);
      if (dado && dado.caminho === window.location.pathname) id = dado.id;
    } catch (erro) {
      return false;
    }
    var alvo = id && document.getElementById(id);
    if (!alvo) return false;
    var menos = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Um instante depois da primeira pintura, para o movimento ser visto.
    setTimeout(function () {
      alvo.scrollIntoView({ behavior: menos ? "auto" : "smooth", block: "start" });
    }, 120);
    return true;
  }

  var y = null;
  function restaurar() {
    if (y !== null) window.scrollTo(0, y);
  }
  document.addEventListener("DOMContentLoaded", function () {
    if (deslizarAteOAlvo()) return;
    y = lerEApagar();
    restaurar();
  });
  // Fontes e abas ainda mexem na altura da página: a posição é reaplicada quando tudo carregou.
  window.addEventListener("load", restaurar);
})();
