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

  // Junto com a posição vai o `id` da linha da tabela que o formulário alterou: na volta ela pisca,
  // porque a mensagem de confirmação fica no topo da página, fora da vista.
  function guardar(form) {
    var linha = form.closest && form.closest("tr[id]");
    try {
      sessionStorage.setItem(
        CHAVE,
        JSON.stringify({
          caminho: window.location.pathname,
          y: window.scrollY,
          linha: linha ? linha.id : null,
        })
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
      return dado && dado.caminho === window.location.pathname ? dado : null;
    } catch (e) {
      return null;
    }
  }

  document.addEventListener("submit", function (e) {
    if (e.target.matches && e.target.matches("form[data-manter-rolagem], form[data-filtros-auto]")) {
      guardar(e.target);
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
        JSON.stringify({
          caminho: destino.pathname,
          id: link.getAttribute("data-rolar-ate"),
          destacar: link.getAttribute("data-destacar"),
        })
      );
    } catch (erro) {
      return; // sem armazenamento, o link segue com a âncora
    }
    e.preventDefault();
    destino.hash = "";
    window.location.assign(destino.href);
  });

  // Uma piscada no elemento que o link quer mostrar (`data-destacar="id"`), quando a rolagem
  // termina: anel e fundo que se dissolvem (componentes.css, `.destaque-piscada`). Com movimento
  // reduzido o destaque fica parado e some.
  function piscar(el) {
    el.classList.remove("destaque-piscada");
    void el.offsetWidth; // reinicia a animação se já estava rodando
    el.classList.add("destaque-piscada");
    setTimeout(function () {
      el.classList.remove("destaque-piscada");
    }, 1600);
  }

  function aoTerminarARolagem(fazer, menos) {
    var feito = false;
    function uma() {
      if (feito) return;
      feito = true;
      fazer();
    }
    // `scrollend` avisa o fim da rolagem suave; se a página já estava no lugar ele não vem, e o
    // tempo cobre os dois casos.
    window.addEventListener("scrollend", uma, { once: true });
    setTimeout(uma, menos ? 150 : 1000);
  }

  function deslizarAteOAlvo() {
    var id = null;
    var destacar = null;
    try {
      var dado = JSON.parse(sessionStorage.getItem(ALVO) || "null");
      sessionStorage.removeItem(ALVO);
      if (dado && dado.caminho === window.location.pathname) {
        id = dado.id;
        destacar = dado.destacar;
      }
    } catch (erro) {
      return false;
    }
    var alvo = id && document.getElementById(id);
    if (!alvo) return false;
    var menos = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Um instante depois da primeira pintura, para o movimento ser visto.
    setTimeout(function () {
      alvo.scrollIntoView({ behavior: menos ? "auto" : "smooth", block: "start" });
      var piscante = destacar && document.getElementById(destacar);
      if (piscante) aoTerminarARolagem(function () { piscar(piscante); }, menos);
    }, 120);
    return true;
  }

  var y = null;
  var linha = null;
  // Quem rola (roda, toque, teclado ou arrastando a barra) antes de a página terminar de carregar
  // manda na posição: a segunda restauração, do `load`, não a desfaz.
  var interagiu = false;
  ["wheel", "touchstart", "keydown", "mousedown"].forEach(function (tipo) {
    window.addEventListener(tipo, function () { interagiu = true; }, { passive: true, once: true });
  });
  function restaurar() {
    if (y !== null) window.scrollTo(0, y);
  }
  document.addEventListener("DOMContentLoaded", function () {
    if (deslizarAteOAlvo()) return;
    var dado = lerEApagar();
    if (dado) {
      y = dado.y;
      linha = dado.linha;
    }
    restaurar();
  });
  // Fontes e abas ainda mexem na altura da página: a posição é reaplicada quando tudo carregou, e
  // só então a linha alterada pisca (se ainda está na lista: um filtro pode tê-la tirado).
  window.addEventListener("load", function () {
    if (!interagiu) restaurar();
    var alterada = linha && document.getElementById(linha);
    linha = null;
    if (alterada) piscar(alterada);
  });
})();
