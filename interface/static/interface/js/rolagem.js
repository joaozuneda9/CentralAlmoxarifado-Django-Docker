/*
 * Mantém a rolagem da página ao enviar um formulário que volta para a mesma página
 * (`form[data-manter-rolagem]` e os filtros `form[data-filtros-auto]`): a lista recarrega e a
 * tela continua onde estava, em vez de voltar ao topo. Carregado no <head> com defer.
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

  var y = null;
  function restaurar() {
    if (y !== null) window.scrollTo(0, y);
  }
  document.addEventListener("DOMContentLoaded", function () {
    y = lerEApagar();
    restaurar();
  });
  // Fontes e abas ainda mexem na altura da página: a posição é reaplicada quando tudo carregou.
  window.addEventListener("load", restaurar);
})();
