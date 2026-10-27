/*
 * Dropdown — a base de todo painel que abre embaixo de um campo, no estilo do painel de
 * resultados da busca de materiais. Carregado com `defer` no <head>.
 *
 * Melhoria progressiva: o <select> ou <input list> original continua na página e é ele quem
 * guarda o valor, dispara `change` e vai no envio do formulário (HTMX e testes não mudam). O
 * script só o esconde e desenha o gatilho e o painel. Sem JavaScript, valem os nativos.
 *
 * A BASE (este arquivo + `.painel-flutuante` e `.dropdown-*` em componentes.css) concentra a casca do
 * painel, abrir e fechar (animados), a navegação por teclado, o ARIA, a posição e o fechamento por
 * clique ou foco fora. Os tipos só dizem como montar o controle e quais linhas desenhar:
 *
 * - select.campo-entrada: seleção simples. Gatilho (botão) + painel com as opções (grupos viram
 *   cabeçalhos). Não há caixa de busca: digitar pula para a opção que começa com o que se digitou
 *   (as letras se acumulam por LIMITE_DIGITACAO ms).
 * - input.campo-entrada[list]: campo com lista. O próprio campo filtra o painel enquanto se digita;
 *   o texto continua livre (quem valida é o servidor).
 * - select.campo-entrada[data-dropdown-digitavel]: select digitável. O controle é um campo de texto como o
 *   do campo com lista (filtra a lista enquanto se digita), mas só vale uma opção dela: o <select> guarda
 *   o valor e o que foi digitado e não escolhido volta ao escolhido ao sair (placa e centro de custo).
 * - select.campo-entrada[data-dropdown-arvore]: cada <optgroup> vira uma pasta (a primeira opção
 *   dele, de valor igual ao rótulo do grupo, é a pasta; as demais, os filhos, ligados por ├─ └─),
 *   fechada até se clicar na seta ou apertar →; escolher a pasta escolhe o grupo inteiro.
 *
 * Fora dos dropdowns, a busca de materiais (pedidos.js) usa a mesma casca (`.painel-flutuante`) e o
 * mesmo abrir e fechar animado, por `window.Dropdown.abrirPainel` e `fecharPainel`.
 *
 * Teclado: ↓ ↑ Home End Enter Esc, e digitar abre a lista; na árvore, → abre a pasta (ou entra
 * nela) e ← fecha (ou volta à pasta). Papéis ARIA de listbox/combobox, e tree na árvore.
 */
(function () {
  "use strict";

  var LIMITE_DIGITACAO = 800;
  var contador = 0;
  var aberto = null;

  function icone(tracos) {
    return (
      '<svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ' +
      'focusable="false">' + tracos + "</svg>"
    );
  }
  var SETA = icone('<path d="m6 9 6 6 6-6"/>');
  var CHECK = icone('<path d="M20 6 9 17l-5-5"/>');

  function norm(texto) {
    return String(texto || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase();
  }

  function criar(tag, classe, texto) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function rotuloDe(campo) {
    var r = campo.id && document.querySelector('label[for="' + campo.id + '"]');
    if (r && !r.id) r.id = campo.id + "-rotulo";
    return r;
  }

  function textoDoRotulo(rotuloEl) {
    return rotuloEl ? rotuloEl.textContent.replace(/\s*\*\s*$/, "").trim() : "Opções";
  }

  // ---- abrir e fechar o painel (a casca `.painel-flutuante`) -----------------------------------
  // Comum a todo painel: o `aberto` o mostra, o `fechando` toca a saída e o `aberto` só sai no fim
  // dela. Sem animação (reduzir movimento) ou com a aba em segundo plano, fecha na hora.

  function painelAberto(p) {
    return p.classList.contains("aberto") && !p.classList.contains("fechando");
  }

  // Devolve "novo" (abriu agora), "reaberto" (estava saindo: fica aberto, sem repetir a entrada) ou
  // "ja" (já estava aberto).
  function abrirPainel(p) {
    if (p.classList.contains("fechando")) {
      p.classList.remove("fechando");
      p.removeEventListener("animationend", p._fimFechamento);
      return "reaberto";
    }
    if (p.classList.contains("aberto")) return "ja";
    p.classList.add("aberto");
    return "novo";
  }

  // `aoFechar` roda quando o painel some de vez. Devolve false se não havia o que fechar.
  function fecharPainel(p, aoFechar) {
    if (!painelAberto(p)) return false;
    var fim = function (e) {
      if (e && e.target !== p) return; // animação de algo dentro do painel
      p.removeEventListener("animationend", fim);
      if (!p.classList.contains("fechando")) return;
      p.classList.remove("fechando", "aberto");
      if (aoFechar) aoFechar();
    };
    p._fimFechamento = fim;
    p.addEventListener("animationend", fim);
    p.classList.add("fechando");
    if (getComputedStyle(p).animationName === "none") fim();
    else setTimeout(fim, 250); // reserva: em segundo plano a animação não roda
    return true;
  }

  // ---- toque fora ---------------------------------------------------------------------------------
  // Quem fecha um painel por um toque fora dele se registra em `aoTocarFora(fn)`; `fn` recebe o
  // elemento tocado. Com o mouse, avisa ao apertar o botão, como sempre. Com o dedo (ou a caneta),
  // só quando ele sai da tela sem ter andado mais que FOLGA_TOQUE: encostar para arrastar a página
  // não fecha nada (e, quando o navegador assume a rolagem, o toque vem cancelado). Um segundo dedo
  // (pinça) também desfaz o toque.
  var FOLGA_TOQUE = 10;
  var aoTocar = [];
  var toque = null;

  function avisarToque(alvo) {
    aoTocar.forEach(function (fn) {
      fn(alvo);
    });
  }
  function aoTocarFora(fn) {
    aoTocar.push(fn);
  }

  document.addEventListener("pointerdown", function (e) {
    if (e.pointerType === "mouse") {
      toque = null;
      avisarToque(e.target);
      return;
    }
    toque = e.isPrimary ? { id: e.pointerId, x: e.clientX, y: e.clientY, alvo: e.target } : null;
  });
  function andou(e) {
    return Math.hypot(e.clientX - toque.x, e.clientY - toque.y) > FOLGA_TOQUE;
  }
  document.addEventListener(
    "pointermove",
    function (e) {
      if (toque && e.pointerId === toque.id && andou(e)) toque = null;
    },
    { passive: true }
  );
  document.addEventListener("pointercancel", function () {
    toque = null;
  });
  // A distância é conferida de novo ao soltar: o navegador pode juntar ou atrasar os `pointermove`.
  document.addEventListener("pointerup", function (e) {
    if (!toque || e.pointerId !== toque.id) return;
    var alvo = toque.alvo;
    var arrastou = andou(e);
    toque = null;
    if (!arrastou) avisarToque(alvo);
  });

  window.Dropdown = {
    abrirPainel: abrirPainel,
    fecharPainel: fecharPainel,
    painelAberto: painelAberto,
    aoTocarFora: aoTocarFora,
  };

  // ---- fontes das opções ------------------------------------------------------------------------

  function opcoesDoSelect(select) {
    var lista = [];
    Array.prototype.forEach.call(select.children, function (filho) {
      if (filho.tagName === "OPTGROUP") {
        Array.prototype.forEach.call(filho.children, function (o) {
          lista.push({ valor: o.value, texto: o.textContent.trim(), grupo: filho.label });
        });
      } else if (filho.tagName === "OPTION") {
        lista.push({ valor: filho.value, texto: filho.textContent.trim(), grupo: "" });
      }
    });
    return lista;
  }

  // Árvore (data-dropdown-arvore): opções soltas (fora de grupo) e um nó por <optgroup>, com a
  // primeira opção como o próprio grupo e as demais como filhos (o texto do filho é o que vem
  // depois do último " › ").
  function arvoreDoSelect(select) {
    var arvore = { soltas: [], grupos: [] };
    Array.prototype.forEach.call(select.children, function (filho) {
      if (filho.tagName === "OPTION") {
        arvore.soltas.push({ valor: filho.value, texto: filho.textContent.trim() });
      } else if (filho.tagName === "OPTGROUP" && filho.children.length) {
        var opcoes = Array.prototype.slice.call(filho.children);
        arvore.grupos.push({
          valor: opcoes[0].value,
          texto: filho.label,
          filhos: opcoes.slice(1).map(function (o) {
            var partes = o.textContent.split(" › ");
            return { valor: o.value, texto: partes[partes.length - 1].trim() };
          }),
        });
      }
    });
    return arvore;
  }

  // ---- painel (comum aos tipos) ------------------------------------------------------------------

  function montarPainel(d, rotulo) {
    var id = "dropdown-" + ++contador;
    d.id = id;
    d.painel = criar("div", "painel-flutuante dropdown-painel");

    // Sem legenda (rótulo e contagem): o painel é só a lista; o rótulo vai no `aria-label` dela.
    d.lista = criar("ul", "dropdown-lista");
    d.lista.id = id + "-lista";
    d.lista.setAttribute("role", d.arvore ? "tree" : "listbox");
    if (d.arvore) d.lista.classList.add("dropdown-arvore");
    d.lista.setAttribute("aria-label", rotulo);
    if (d.tipo === "select") d.lista.tabIndex = -1;
    d.painel.appendChild(d.lista);
    d.raiz.appendChild(d.painel);

    // O foco fica onde está (o campo ou a lista): clicar no painel não o tira de lá.
    d.painel.addEventListener("mousedown", function (e) {
      e.preventDefault();
    });
    d.lista.addEventListener("click", function (e) {
      var seta = e.target.closest("[data-alternar]");
      if (seta) return alternar(d, seta.getAttribute("data-alternar"), true);
      var li = e.target.closest("[data-i]");
      if (li) escolher(d, Number(li.getAttribute("data-i")));
    });
    d.lista.addEventListener("mousemove", function (e) {
      var li = e.target.closest("[data-i]");
      if (li && Number(li.getAttribute("data-i")) !== d.ativo) ativar(d, Number(li.getAttribute("data-i")), false);
    });
  }

  // Quem recebe o foco e o `aria-activedescendant`: o campo de texto visível (campo com lista e select
  // digitável, onde o <select> escondido só guarda o valor) ou a lista.
  function teclado(d) {
    return d.tipo === "combo" ? d.controle : d.lista;
  }

  function selecionada(d, o) {
    if (d.tipo === "select" || d.digitavel) return o.valor === d.campo.value;
    return d.campo.value !== "" && norm(o.valor) === norm(d.campo.value);
  }

  function linhaCheck(li) {
    var check = criar("span", "dropdown-check");
    check.innerHTML = CHECK;
    li.appendChild(check);
  }

  function renderizar(d) {
    if (d.arvore) return renderizarArvore(d);
    var palavras = norm(d.termo).split(/\s+/).filter(Boolean);
    d.visiveis = d.opcoes.filter(function (o) {
      var t = norm(o.texto);
      return palavras.every(function (p) {
        return t.indexOf(p) !== -1;
      });
    });
    d.lista.innerHTML = "";
    var grupo = null;
    var escolhida = -1;
    d.visiveis.forEach(function (o, i) {
      if (o.grupo && o.grupo !== grupo) {
        var g = criar("li", "dropdown-grupo rotulo-secao", o.grupo);
        g.setAttribute("role", "presentation");
        d.lista.appendChild(g);
      }
      grupo = o.grupo;
      var li = criar("li", "dropdown-opcao");
      li.id = d.id + "-o" + i;
      li.setAttribute("role", "option");
      li.setAttribute("data-i", i);
      var marcada = selecionada(d, o);
      li.setAttribute("aria-selected", marcada ? "true" : "false");
      if (marcada && escolhida < 0) escolhida = i;
      li.appendChild(criar("span", "dropdown-texto", o.texto));
      linhaCheck(li);
      d.lista.appendChild(li);
    });
    if (!d.visiveis.length) {
      var vazio = criar("li", "dropdown-sem-opcoes texto-secundario", "Nenhuma opção encontrada.");
      vazio.setAttribute("role", "presentation");
      d.lista.appendChild(vazio);
    }
    var escolheOPrimeiro = (d.tipo === "select" || d.digitavel) && d.visiveis.length;
    ativar(d, escolhida >= 0 ? escolhida : escolheOPrimeiro ? 0 : -1, true);
  }

  function renderizarArvore(d) {
    d.visiveis = d.arvore.soltas.map(function (o) {
      return { valor: o.valor, texto: o.texto, nivel: 1 };
    });
    d.arvore.grupos.forEach(function (g) {
      var abrir = g.filhos.length > 0 && !!d.abertos[g.valor];
      d.visiveis.push({ valor: g.valor, texto: g.texto, nivel: 1, grupo: g, aberto: abrir });
      if (!abrir) return;
      g.filhos.forEach(function (f, i) {
        d.visiveis.push({ valor: f.valor, texto: f.texto, nivel: 2, pai: g, ultimo: i === g.filhos.length - 1 });
      });
    });
    d.lista.innerHTML = "";
    var escolhida = -1;
    d.visiveis.forEach(function (o, i) {
      var li = criar("li", "dropdown-opcao dropdown-no" + (o.nivel === 2 ? " dropdown-filho" : ""));
      li.id = d.id + "-o" + i;
      li.setAttribute("role", "treeitem");
      li.setAttribute("aria-level", o.nivel);
      li.setAttribute("data-i", i);
      var marcada = selecionada(d, o);
      li.setAttribute("aria-selected", marcada ? "true" : "false");
      if (marcada && escolhida < 0) escolhida = i;
      // À esquerda, o ramo (filho) ou a quantidade de subgrupos (pasta); à direita, depois do
      // check, o botão que abre a pasta, com a seta para baixo que gira ao abrir.
      var n = o.grupo ? o.grupo.filhos.length : 0;
      if (o.nivel === 2) {
        var ramo = criar("span", "dropdown-ramo", o.ultimo ? "└─" : "├─");
        ramo.setAttribute("aria-hidden", "true");
        li.appendChild(ramo);
      } else if (n) {
        var qtd = criar("span", "dropdown-qtd", String(n));
        qtd.setAttribute("aria-label", n + (n === 1 ? " subgrupo" : " subgrupos"));
        li.appendChild(qtd);
      } else {
        li.appendChild(criar("span", "dropdown-qtd dropdown-qtd-vazia"));
      }
      li.appendChild(criar("span", "dropdown-texto", o.texto));
      linhaCheck(li);
      if (n) {
        li.setAttribute("aria-expanded", o.aberto ? "true" : "false");
        var seta = criar("span", "dropdown-alternar");
        seta.innerHTML = SETA;
        seta.setAttribute("data-alternar", o.valor);
        seta.setAttribute("aria-hidden", "true");
        seta.title = o.aberto
          ? "Esconder os subgrupos"
          : n === 1
            ? "Ver o subgrupo"
            : "Ver os " + n + " subgrupos";
        li.appendChild(seta);
      }
      d.lista.appendChild(li);
    });
    ativar(d, escolhida >= 0 ? escolhida : 0, true);
  }

  // Abre ou fecha a pasta do grupo. Pelo teclado, mantém ativa a linha que estava (ou a pasta, se
  // a linha sumiu ao fechar); pelo clique na seta (`naPasta`), ativa a própria pasta.
  function alternar(d, valor, naPasta) {
    d.abertos[valor] = !d.abertos[valor];
    var atual = d.visiveis[d.ativo];
    var manter = !naPasta && atual && (!atual.pai || d.abertos[atual.pai.valor]) ? atual.valor : valor;
    renderizar(d);
    for (var i = 0; i < d.visiveis.length; i++) {
      if (d.visiveis[i].valor === manter) ativar(d, i, true);
    }
    // Ao abrir, rola para mostrar os filhos sem tirar a pasta de vista.
    if (!d.abertos[valor]) return;
    var filhos = d.lista.querySelectorAll(".dropdown-filho");
    var pasta = d.lista.querySelector('[data-alternar="' + CSS.escape(valor) + '"]');
    for (var j = 0; j < filhos.length; j++) {
      var o = d.visiveis[Number(filhos[j].getAttribute("data-i"))];
      if (o && o.pai && o.pai.valor === valor && o.ultimo) filhos[j].scrollIntoView({ block: "nearest" });
    }
    if (pasta) pasta.parentNode.scrollIntoView({ block: "nearest" });
  }

  function ativar(d, i, rolar) {
    var antigo = d.lista.querySelector("[data-ativa]");
    if (antigo) antigo.removeAttribute("data-ativa");
    d.ativo = i;
    var alvo = teclado(d);
    var li = i >= 0 ? d.lista.querySelector('[data-i="' + i + '"]') : null;
    if (!li) {
      alvo.removeAttribute("aria-activedescendant");
      return;
    }
    li.setAttribute("data-ativa", "");
    alvo.setAttribute("aria-activedescendant", li.id);
    if (rolar) li.scrollIntoView({ block: "nearest" });
  }

  function abrir(d, termo) {
    if (aberto && aberto !== d) fechar(aberto, false);
    d.termo = termo || "";
    // Na árvore, a pasta do subgrupo escolhido já abre aberta.
    if (d.arvore) {
      d.arvore.grupos.forEach(function (g) {
        g.filhos.forEach(function (f) {
          if (f.valor === d.campo.value) d.abertos[g.valor] = true;
        });
      });
    }
    renderizar(d);
    abrirPainel(d.painel);
    // Coluna perto da borda direita: o painel (mais largo que ela) abre para a esquerda.
    d.painel.style.left = "";
    d.painel.style.right = "";
    if (d.painel.getBoundingClientRect().right > window.innerWidth - 8) {
      d.painel.style.left = "auto";
      d.painel.style.right = "0";
    }
    d.raiz.setAttribute("data-aberto", "");
    d.controle.setAttribute("aria-expanded", "true");
    aberto = d;
    if (d.tipo === "select") d.lista.focus({ preventScroll: true });
    var li = d.lista.querySelector("[data-ativa]");
    if (li) li.scrollIntoView({ block: "nearest" });
  }

  function fechar(d, devolverFoco) {
    fecharPainel(d.painel);
    if (d.digitavel) atualizarGatilho(d); // o que foi digitado e não escolhido não vale: volta ao escolhido
    d.raiz.removeAttribute("data-aberto");
    d.controle.setAttribute("aria-expanded", "false");
    if (aberto === d) aberto = null;
    // Gatilho escondido (o filtro de grupo abre direto do <summary> do <details>): o painel pertence ao
    // <details>, que fecha junto (senão ficaria aberto, com a seta para cima e nada embaixo), e o foco
    // volta ao resumo.
    var detalhes = d.controle.offsetParent === null ? d.raiz.closest("details") : null;
    if (detalhes) detalhes.open = false;
    if (!devolverFoco) return;
    var alvo = detalhes ? detalhes.querySelector(":scope > summary") : d.controle;
    if (alvo) alvo.focus();
  }

  function escolher(d, i) {
    var o = d.visiveis[i];
    if (!o) return;
    d.campo.value = o.valor;
    if (d.tipo === "select" || d.digitavel) atualizarGatilho(d);
    d.campo.dispatchEvent(new Event("change", { bubbles: true }));
    fechar(d, d.tipo === "select");
  }

  // Mostra no controle o que o <select> guarda: o texto no gatilho (botão) ou, no select digitável, no campo
  // (vazio quando a opção é a sem valor: aí aparece o `placeholder`, que é o rótulo dela).
  function atualizarGatilho(d) {
    var o = d.campo.options[d.campo.selectedIndex];
    if (d.digitavel) {
      d.controle.value = o && d.campo.value !== "" ? o.textContent.trim() : "";
      return;
    }
    d.texto.textContent = o ? o.textContent.trim() : "";
    d.controle.classList.toggle("dropdown-vazio", d.campo.value === "");
  }

  // Seleção simples sem busca: digitar pula para a primeira opção que começa com o que se digitou.
  // As letras se acumulam até LIMITE_DIGITACAO ms de pausa; uma letra só, repetida, anda pelas opções.
  function pularPara(d, tecla) {
    clearTimeout(d.pausa);
    d.digitado = (d.digitado || "") + norm(tecla);
    d.pausa = setTimeout(function () {
      d.digitado = "";
    }, LIMITE_DIGITACAO);
    // A mesma letra repetida ("aa", "aaa") conta como uma letra só e anda pelas opções a partir da ativa,
    // como no <select> nativo (o acumulado volta a ela: "a", "a", "b" busca "ab"); letras diferentes
    // buscam o prefixo inteiro, desde o começo.
    if (/^(.)\1+$/.test(d.digitado)) d.digitado = d.digitado.charAt(0);
    var busca = d.digitado;
    var n = d.visiveis.length;
    var inicio = busca.length === 1 ? d.ativo + 1 : 0;
    for (var k = 0; k < n; k++) {
      var i = (inicio + k) % n;
      if (norm(d.visiveis[i].texto).indexOf(busca) === 0) return ativar(d, i, true);
    }
  }

  function aoTeclar(d, e) {
    var k = e.key;
    var imprimivel = k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey;
    if (aberto !== d) {
      if (k === "ArrowDown" || k === "ArrowUp") {
        e.preventDefault();
        abrir(d, "");
      } else if (d.tipo === "select" && (k === "Enter" || k === " ")) {
        e.preventDefault();
        abrir(d, "");
      } else if (d.digitavel && k === "Enter") {
        e.preventDefault(); // não envia o formulário: abre a lista
        abrir(d, "");
      } else if (d.tipo === "select" && imprimivel) {
        e.preventDefault();
        abrir(d, "");
        pularPara(d, k);
      }
      return;
    }
    if (d.arvore && (k === "ArrowRight" || k === "ArrowLeft")) {
      e.preventDefault();
      var no = d.visiveis[d.ativo];
      if (!no) return;
      if (k === "ArrowRight" && no.grupo && no.grupo.filhos.length) {
        if (!no.aberto) alternar(d, no.valor);
        else ativar(d, d.ativo + 1, true);
      } else if (k === "ArrowLeft" && no.pai) {
        for (var j = 0; j < d.visiveis.length; j++) {
          if (d.visiveis[j].grupo === no.pai) return ativar(d, j, true);
        }
      } else if (k === "ArrowLeft" && no.aberto) {
        alternar(d, no.valor);
      }
      return;
    }
    if (k === "ArrowDown" || k === "ArrowUp") {
      e.preventDefault();
      var passo = k === "ArrowDown" ? 1 : -1;
      var proximo = d.ativo < 0 ? (passo > 0 ? 0 : d.visiveis.length - 1) : d.ativo + passo;
      ativar(d, Math.max(0, Math.min(d.visiveis.length - 1, proximo)), true);
    } else if ((k === "Home" || k === "End") && e.target === d.lista) {
      e.preventDefault();
      ativar(d, k === "Home" ? 0 : d.visiveis.length - 1, true);
    } else if (k === "Enter" || (k === " " && e.target === d.lista && !d.digitado)) {
      if (d.ativo >= 0) {
        e.preventDefault();
        escolher(d, d.ativo);
      } else if (d.tipo === "select" || d.digitavel) {
        e.preventDefault();
      } else {
        fechar(d, false);
      }
    } else if (k === "Escape") {
      // Não deixa o Esc chegar à busca de materiais (pedidos.js), que também o escuta.
      e.preventDefault();
      e.stopPropagation();
      fechar(d, true);
    } else if (k === "Tab") {
      fechar(d, false);
    } else if (d.tipo === "select" && imprimivel) {
      e.preventDefault();
      pularPara(d, k);
    }
  }

  // ---- tipos: só montam o controle; o resto é a base ----------------------------------------------

  // Liga ao dropdown o que todo tipo tem: painel, teclado e a trava `data-travado`.
  function finalizar(d, rotulo) {
    montarPainel(d, rotulo);
    d.controle.setAttribute("aria-controls", d.lista.id);
    d.controle.addEventListener("keydown", function (e) {
      aoTeclar(d, e);
    });
    d.lista.addEventListener("keydown", function (e) {
      aoTeclar(d, e);
    });
    d.campo.setAttribute("data-dropdown-pronto", "");
    // `data-travado` no <select> trava só o dropdown: o <select> segue habilitado, para o valor
    // ir no envio (campo `disabled` não vai).
    if (d.campo.tagName !== "SELECT") return;
    function sincronizarTrava() {
      var travado = d.campo.hasAttribute("data-travado");
      d.controle.disabled = travado;
      if (travado && aberto === d) fechar(d, false);
    }
    new MutationObserver(sincronizarTrava).observe(d.campo, {
      attributes: true,
      attributeFilter: ["data-travado"],
    });
    sincronizarTrava();
  }

  // Campo de texto que abre a lista e a filtra enquanto se digita: o do campo com lista e o do select
  // digitável (o mesmo comportamento; muda só o que o campo guarda).
  function ligarCampoDeTexto(d) {
    var input = d.controle;
    input.addEventListener("focus", function () {
      if (aberto !== d) abrir(d, "");
      if (d.digitavel) input.select(); // digitar já troca o escolhido
    });
    input.addEventListener("click", function () {
      if (aberto !== d) abrir(d, "");
    });
    input.addEventListener("input", function () {
      if (aberto === d) {
        d.termo = input.value;
        renderizar(d);
      } else {
        abrir(d, input.value);
      }
    });
  }

  // Select digitável (`data-dropdown-digitavel`): o controle é um campo de texto como o do campo com
  // lista, mas só vale uma opção da lista (o <select> guarda o valor): o que foi digitado e não
  // escolhido volta ao escolhido ao sair.
  function montarDigitavel(select) {
    var rotuloEl = rotuloDe(select);
    var d = { tipo: "combo", digitavel: true, campo: select, opcoes: opcoesDoSelect(select), abertos: {} };

    d.raiz = criar("div", "dropdown");
    select.parentNode.insertBefore(d.raiz, select);
    d.raiz.appendChild(select);
    select.classList.add("visually-hidden");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    var input = criar("input", select.className.replace("visually-hidden", "").trim() + " dropdown-combo");
    input.type = "text";
    input.id = select.id ? select.id + "-gatilho" : "dropdown-gatilho-" + ++contador;
    input.autocomplete = "off";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-haspopup", "listbox");
    input.setAttribute("aria-expanded", "false");
    if (rotuloEl) input.setAttribute("aria-labelledby", rotuloEl.id);
    var vazia = d.opcoes.filter(function (o) {
      return o.valor === "";
    })[0];
    if (vazia) input.placeholder = vazia.texto;
    d.controle = input;
    d.raiz.insertBefore(input, select);
    var seta = criar("span", "dropdown-seta dropdown-seta-campo");
    seta.innerHTML = SETA;
    d.raiz.appendChild(seta);

    finalizar(d, textoDoRotulo(rotuloEl));
    atualizarGatilho(d);
    ligarCampoDeTexto(d);
    // O rótulo (<label for>) e o foco programático chegam ao <select>: passam para o campo.
    select.addEventListener("focus", function () {
      input.focus();
    });
    // Alteração de fora (outro script troca o valor e dispara `change`).
    select.addEventListener("change", function () {
      atualizarGatilho(d);
    });
  }

  function montarSelect(select) {
    if (select.hasAttribute("data-dropdown-digitavel")) return montarDigitavel(select);
    var rotuloEl = rotuloDe(select);
    var d = { tipo: "select", campo: select, opcoes: opcoesDoSelect(select) };
    d.arvore = select.hasAttribute("data-dropdown-arvore") ? arvoreDoSelect(select) : null;
    d.abertos = {};

    d.raiz = criar("div", "dropdown");
    select.parentNode.insertBefore(d.raiz, select);
    d.raiz.appendChild(select);
    select.classList.add("visually-hidden");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    d.controle = criar("button", select.className.replace("visually-hidden", "").trim() + " dropdown-gatilho");
    d.controle.type = "button";
    d.controle.id = select.id ? select.id + "-gatilho" : "dropdown-gatilho-" + ++contador;
    d.controle.setAttribute("aria-haspopup", d.arvore ? "tree" : "listbox");
    d.controle.setAttribute("aria-expanded", "false");
    if (rotuloEl) d.controle.setAttribute("aria-labelledby", rotuloEl.id + " " + d.controle.id);
    d.texto = criar("span", "dropdown-valor");
    d.controle.appendChild(d.texto);
    var seta = criar("span", "dropdown-seta");
    seta.innerHTML = SETA;
    d.controle.appendChild(seta);
    d.raiz.insertBefore(d.controle, select);

    finalizar(d, textoDoRotulo(rotuloEl));
    atualizarGatilho(d);

    d.controle.addEventListener("click", function () {
      if (aberto === d) fechar(d, true);
      else abrir(d, "");
    });
    // O rótulo (<label for>) e o foco programático chegam ao <select>: passam para o gatilho.
    select.addEventListener("focus", function () {
      d.controle.focus();
    });
    // Alteração de fora (outro script troca o valor e dispara `change`).
    select.addEventListener("change", function () {
      atualizarGatilho(d);
    });
  }

  function montarCombo(input) {
    var datalist = document.getElementById(input.getAttribute("list"));
    if (!datalist) return;
    var opcoes = Array.prototype.map.call(datalist.options, function (o) {
      return { valor: o.value, texto: o.value, grupo: "" };
    });
    var d = { tipo: "combo", campo: input, controle: input, opcoes: opcoes };

    input.removeAttribute("list"); // some o dropdown nativo do navegador
    d.raiz = criar("div", "dropdown");
    input.parentNode.insertBefore(d.raiz, input);
    d.raiz.appendChild(input);
    input.classList.add("dropdown-combo");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-haspopup", "listbox");
    input.setAttribute("aria-expanded", "false");
    var seta = criar("span", "dropdown-seta dropdown-seta-campo");
    seta.innerHTML = SETA;
    d.raiz.appendChild(seta);

    finalizar(d, textoDoRotulo(rotuloDe(input)));
    ligarCampoDeTexto(d);
  }

  // ---- início e fechamento ------------------------------------------------------------------------

  function iniciar(raiz) {
    if (aberto && !document.contains(aberto.raiz)) aberto = null;
    raiz.querySelectorAll("select.campo-entrada:not([multiple]):not([data-dropdown-pronto])").forEach(montarSelect);
    raiz.querySelectorAll("input.campo-entrada[list]:not([data-dropdown-pronto])").forEach(montarCombo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    iniciar(document);
  });
  document.addEventListener("htmx:after:swap", function () {
    iniciar(document);
  });

  // Painel que brota do <summary> de um <details> (o filtro de grupo): tocar no próprio resumo não conta
  // como "fora" (senão o painel e o <details> fecham no toque e o clique os abriria de novo): quem fecha
  // é o clique do resumo, e o `toggle` abaixo fecha o painel junto.
  function noResumoDoPainel(d, alvo) {
    var detalhes = d.raiz.closest("details");
    var resumo = alvo.closest && alvo.closest("summary");
    return !!(detalhes && resumo && resumo.parentNode === detalhes);
  }

  aoTocarFora(function (alvo) {
    if (aberto && !aberto.raiz.contains(alvo) && !noResumoDoPainel(aberto, alvo)) fechar(aberto, false);
  });
  document.addEventListener("focusin", function (e) {
    if (aberto && !aberto.raiz.contains(e.target) && !noResumoDoPainel(aberto, e.target)) fechar(aberto, false);
  });
  // `toggle` não sobe pela árvore: escuta na captura. Fechar o <details> do painel fecha o painel.
  document.addEventListener(
    "toggle",
    function (e) {
      if (aberto && e.target.tagName === "DETAILS" && !e.target.open && e.target.contains(aberto.raiz)) {
        fechar(aberto, false);
      }
    },
    true
  );
})();
