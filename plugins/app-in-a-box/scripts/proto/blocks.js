/* Block renderers: one function per block type in design/prototype.json.
   Everything is built with DOM calls and textContent, never innerHTML with spec
   strings, so copy can't inject markup. Icons are the only innerHTML, and they come
   from the kit's own icons.json. */
var Proto = (function () {
  "use strict";
  var CFG = JSON.parse(document.getElementById("proto-config").textContent);
  var uid = 0;

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") n.className = v;
        else if (k === "text") n.textContent = v;
        else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v === true ? "" : String(v));
      });
    }
    (kids || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }

  function icon(name, style, cls) {
    var body = CFG.icons[name] || "";
    var sharp = style === "sharp";
    var span = el("span", { class: "ic" + (cls ? " " + cls : ""), "aria-hidden": "true" });
    span.innerHTML = '<svg viewBox="0 0 24 24" focusable="false">' +
      body.replace(/\{r\}/g, sharp ? "0" : "3").replace(/\{r2\}/g, sharp ? "0" : "1.5") + "</svg>";
    return span;
  }

  function press(node, action, ctx) {
    if (action) node.addEventListener("click", function () { ctx.act(action); });
    return node;
  }

  var R = {};

  R.header = function (b, ctx) {
    return el("div", { class: "b-header" }, [
      // a plain dim line (date, context), never a tracked uppercase kicker
      b.eyebrow ? el("p", { class: "t-secondary eyebrow", text: ctx.t(b.eyebrow) }) : null,
      el("h1", { class: "t-title", text: ctx.t(b.title) }),
      b.subtitle ? el("p", { class: "t-secondary", text: ctx.t(b.subtitle) }) : null
    ]);
  };

  R.text = function (b, ctx) {
    return el("p", { class: "t-body b-text" + (b.style === "secondary" ? " secondary" : ""), text: ctx.t(b.body) });
  };

  R.list = function (b, ctx) {
    var rows = el("div", { class: "rows surface-card", role: "list" });
    b.items.forEach(function (it) {
      var kids = [
        it.icon ? el("span", { class: "lead-ic" }, [icon(it.icon, ctx.iconStyle)]) : null,
        el("span", { class: "row-text" }, [
          el("span", { class: "row-title", text: ctx.t(it.title) }),
          it.meta ? el("span", { class: "row-meta", text: ctx.t(it.meta) }) : null
        ]),
        it.trailing ? el("span", { class: "row-trailing", text: ctx.t(it.trailing) }) : null,
        it.action ? icon("chevron", ctx.iconStyle, "chev") : null
      ];
      var row = it.action
        ? press(el("button", { class: "row press", type: "button" }, kids), it.action, ctx)
        : el("div", { class: "row" }, kids);
      rows.appendChild(el("div", { role: "listitem" }, [row]));
    });
    return el("div", { class: "b-list" }, [
      b.title ? el("h2", { class: "t-meta", text: ctx.t(b.title) }) : null, rows
    ]);
  };

  R.card = function (b, ctx) {
    var kids = [
      b.icon ? el("span", { class: "lead-ic" }, [icon(b.icon, ctx.iconStyle)]) : null,
      el("span", { class: "card-text" }, [
        b.eyebrow ? el("span", { class: "t-meta", text: ctx.t(b.eyebrow) }) : null,
        el("span", { class: "t-heading", text: ctx.t(b.title) }),
        b.body ? el("span", { class: "t-secondary", text: ctx.t(b.body) }) : null
      ]),
      b.action ? icon("chevron", ctx.iconStyle, "chev") : null
    ];
    return b.action
      ? press(el("button", { class: "b-card surface-card press", type: "button" }, kids), b.action, ctx)
      : el("div", { class: "b-card surface-card" }, kids);
  };

  function button(label, style, iconName, action, ctx) {
    return press(el("button", { class: "b-button press " + style, type: "button" }, [
      iconName ? icon(iconName, ctx.iconStyle) : null, el("span", { text: label })
    ]), action, ctx);
  }
  R.button = function (b, ctx) { return button(ctx.t(b.label), b.style, b.icon, b.action, ctx); };

  function choiceGroup(b, ctx, rowClass, itemClass, wrap) {
    var label = b.label ? ctx.t(b.label) : null;
    var id = "g" + (++uid);
    var group = el("div", { class: rowClass, role: "group", "aria-labelledby": label ? id : null,
      "aria-label": label ? null : "Options" });
    var sel = typeof b.selected === "number" ? b.selected : 0;
    b.options.forEach(function (o, i) {
      var btn = el("button", { class: itemClass, type: "button", "aria-pressed": String(i === sel) },
        [wrap ? el("span", { text: ctx.t(o) }) : ctx.t(o)]);
      btn.addEventListener("click", function () {
        Array.prototype.forEach.call(group.children, function (c) { c.setAttribute("aria-pressed", String(c === btn)); });
      });
      group.appendChild(btn);
    });
    return [label ? el("p", { class: "t-meta", id: id, text: label }) : null, group];
  }
  R.chips = function (b, ctx) { return el("div", { class: "b-chips" }, choiceGroup(b, ctx, "chip-row", "chip", true)); };
  R.segmented = function (b, ctx) { return el("div", { class: "b-seg" }, choiceGroup(b, ctx, "seg", "", false)); };

  R.input = function (b, ctx) {
    var id = "in" + (++uid);
    return el("div", { class: "b-input" }, [
      el("label", { for: id, text: ctx.t(b.label) }),
      el("input", { id: id, type: "text", autocomplete: "off",
        placeholder: b.placeholder ? ctx.t(b.placeholder) : null, value: b.value ? ctx.t(b.value) : null })
    ]);
  };

  R.stat = function (b, ctx) {
    return el("div", { class: "b-stat surface-card" }, [
      el("p", { class: "t-meta" }, [b.icon ? icon(b.icon, ctx.iconStyle) : null, ctx.t(b.label)]),
      el("p", { class: "stat-value", text: ctx.t(b.value) }),
      b.hint ? el("p", { class: "t-secondary", text: ctx.t(b.hint) }) : null
    ]);
  };

  R.progress = function (b, ctx) {
    var pct = Math.round(b.value * 100);
    var label = ctx.t(b.label);
    return el("div", { class: "b-progress surface-card" }, [
      el("div", { class: "prog-head" }, [el("b", { text: label }), el("span", { class: "t-mono", text: pct + "%" })]),
      el("div", { class: "track", role: "progressbar", "aria-label": label, "aria-valuemin": "0",
        "aria-valuemax": "100", "aria-valuenow": String(pct) }, [
        el("div", { class: "fill", style: "width:" + pct + "%" })
      ]),
      b.hint ? el("p", { class: "t-secondary", text: ctx.t(b.hint) }) : null
    ]);
  };

  R.empty = function (b, ctx) {
    return el("div", { class: "b-empty" }, [
      el("div", { class: "empty-art" }, [icon(b.icon || "plus", ctx.iconStyle)]),
      el("h2", { class: "t-heading", text: ctx.t(b.title) }),
      el("p", { class: "t-secondary", text: ctx.t(b.body) }),
      b.action ? button(ctx.t(b.action.label), "primary", null, b.action, ctx) : null
    ]);
  };

  R.image = function (b, ctx) {
    var ratio = (b.ratio || "16:9").split(":");
    var label = b.label ? ctx.t(b.label) : "Image";
    var box = el("div", { class: "b-image", role: "img", "aria-label": label,
      style: "aspect-ratio:" + ratio[0] + "/" + ratio[1] });
    var art = el("span", { "aria-hidden": "true" });
    art.innerHTML = '<svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" fill="none" stroke="currentColor" stroke-width="1.5">' +
      '<circle cx="250" cy="52" r="22"/><path d="M0 150l80-62 58 44 52-34 130 82"/><path d="M0 180l110-70 70 48 60-30 80 52"/></svg>';
    box.appendChild(art);
    if (b.label) box.appendChild(el("span", { class: "t-meta", text: label }));
    return box;
  };

  R.divider = function (b, ctx) {
    return el("div", { class: "b-divider", role: "separator" }, [b.label ? el("span", { class: "t-meta", text: ctx.t(b.label) }) : null]);
  };

  R.toast = function () { return null; }; // shown by the runtime when the screen appears

  function anno(b) {
    var s = b.type + " → " + (CFG.components[b.type] || b.type);
    if (b.feature) s += " · feature: " + b.feature;
    if (b.note) s += " · " + b.note;
    return s;
  }

  /* Render a block list. Consecutive stat blocks share a 2-up grid. */
  function renderBlocks(blocks, ctx) {
    var out = [], grid = null, i = 0;
    blocks.forEach(function (b) {
      var node = R[b.type] ? R[b.type](b, ctx) : null;
      if (!node) { grid = null; return; }
      var blk = el("div", { class: "blk", "data-block": b.type, "data-anno": anno(b),
        "data-feature": b.feature || null }, [node]);
      if (b.type === "stat") {
        if (!grid) {
          grid = el("div", { class: "stat-grid", style: "--i:" + (i++) });
          out.push(grid);
        }
        grid.appendChild(blk);
        return;
      }
      grid = null;
      blk.style.setProperty("--i", String(i++));
      out.push(blk);
    });
    return out;
  }

  return { CFG: CFG, el: el, icon: icon, renderBlocks: renderBlocks, renderers: R };
})();
