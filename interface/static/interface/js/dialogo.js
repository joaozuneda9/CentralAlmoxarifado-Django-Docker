/*
 * Diálogo de confirmação (`dialog.dialogo-confirmacao`, componentes.css): abre e fecha por atributos.
 * Carregado no <head> com defer, em todas as páginas.
 *
 *   <button type="button" data-abrir-dialogo="id" hidden>   abre o <dialog id="id"> (showModal)
 *   <button type="button" data-fechar-dialogo>               fecha o diálogo em que está
 *
 * O clique no fundo e o Esc também fecham. Sem JavaScript o diálogo vem com `open` e fica à vista
 * na página; com ele, é fechado ao carregar e só abre pelo botão (ou por outro script, como o
 * pedidos.js depois de imprimir). Os botões que o abrem vêm `hidden` e este script os mostra.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-abrir-dialogo][hidden]").forEach(function (b) {
      b.hidden = false;
    });
    document.querySelectorAll("dialog.dialogo-confirmacao[open]").forEach(function (d) {
      d.close();
    });
  });

  document.addEventListener("click", function (e) {
    var alvo = e.target;
    if (!alvo.closest) return;
    var abrir = alvo.closest("[data-abrir-dialogo]");
    if (abrir) {
      var dialogo = document.getElementById(abrir.getAttribute("data-abrir-dialogo"));
      if (dialogo && !dialogo.open) dialogo.showModal();
      return;
    }
    var fechar = alvo.closest("[data-fechar-dialogo]");
    if (fechar) {
      fechar.closest("dialog").close();
      return;
    }
    // O fundo do modal é o próprio <dialog> (o corpo cobre todo o resto).
    if (alvo.matches("dialog.dialogo-confirmacao")) alvo.close();
  });
})();
