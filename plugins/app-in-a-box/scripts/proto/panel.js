/* The control panel beside (or, on narrow screens, under) the phone. It owns no
   state: it renders from the runtime's state and calls back through `api`. Every
   control is a native radio, a role="switch" button or a plain button, so it works
   from the keyboard and reads correctly in a screen reader. */
Proto.panel = (function () {
  "use strict";
  var el = Proto.el, CFG = Proto.CFG;
  var api, body, screenBox, mapList, radios = {}, switches = {}, annotSwitch, copied, textarea, lastScreen = null;
  var LABELS = {
    light: "Light", dark: "Dark", compact: "Compact", regular: "Regular", airy: "Airy",
    calm: "Calm", lively: "Lively", playful: "Playful", "default": "Default", empty: "Empty"
  };
  function label(v) { return LABELS[v] || v; }

  function seg(name, title, hint, values, onChange, labeller) {
    var id = "pl-" + name;
    var group = el("div", { class: "p-seg", role: "radiogroup", "aria-labelledby": id });
    radios[name] = [];
    values.forEach(function (v) {
      var input = el("input", { class: "sr-only", type: "radio", name: "p-" + name, value: v });
      input.addEventListener("change", function () { if (input.checked) onChange(v); });
      radios[name].push(input);
      group.appendChild(el("label", null, [input, el("span", { text: labeller ? labeller(v) : label(v) })]));
    });
    return el("div", { class: "p-row" }, [
      el("span", { class: "p-label", id: id, text: title }), group,
      hint ? el("p", { class: "p-hint", text: hint }) : null
    ]);
  }

  function setRadio(name, value) {
    (radios[name] || []).forEach(function (r) { r.checked = r.value === value; });
  }

  function sw(title, sub, onToggle) {
    var b = el("button", { class: "p-switch", type: "button", role: "switch", "aria-checked": "false" }, [
      el("span", { class: "p-switch-text" }, [el("b", { text: title }), sub ? el("small", { text: sub }) : null]),
      el("span", { class: "p-track", "aria-hidden": "true" })
    ]);
    b.addEventListener("click", function () { onToggle(b.getAttribute("aria-checked") !== "true"); });
    return b;
  }

  function directionCards(spec) {
    var id = "pl-direction";
    var wrap = el("div", { class: "p-dirs", role: "radiogroup", "aria-labelledby": id });
    radios.direction = [];
    spec.directions.forEach(function (d) {
      var input = el("input", { class: "sr-only", type: "radio", name: "p-direction", value: d.id });
      input.addEventListener("change", function () { if (input.checked) api.set("direction", d.id); });
      radios.direction.push(input);
      var art = el("span", { class: "p-dir-art", "aria-hidden": "true", "data-dir": d.id }, ["Aa", el("i")]);
      var sw_ = el("span", { class: "p-swatches", "aria-hidden": "true", "data-dir": d.id }, [el("i"), el("i"), el("i"), el("i")]);
      wrap.appendChild(el("label", { class: "p-dir" }, [input, el("span", { class: "p-dir-card" }, [
        art, el("span", null, [
          el("span", { class: "p-dir-name", text: api.t(d.label) }),
          el("span", { class: "p-dir-why", text: api.t(d.why) }), sw_
        ])
      ])]));
    });
    return el("div", { class: "p-row" }, [el("span", { class: "p-label", id: id, text: "Direction" }), wrap]);
  }

  function paintDirections(mode) {
    Array.prototype.forEach.call(body.querySelectorAll("[data-dir]"), function (n) {
      var pal = CFG.palettes[n.getAttribute("data-dir")][mode];
      if (n.classList.contains("p-dir-art")) {
        n.style.background = pal.bg; n.style.color = pal.ink;
        n.style.fontFamily = '"' + CFG.fonts[n.getAttribute("data-dir")] + '", system-ui, sans-serif';
        n.lastChild.style.background = pal.accent;
      } else {
        [pal.bg, pal.surfaceRaised, pal.accent, pal.ink].forEach(function (c, i) { n.children[i].style.background = c; });
      }
    });
  }

  function build(a) {
    api = a;
    var spec = api.spec;
    body = document.getElementById("panel-body");
    var tagline = spec.app.tagline ? api.t(spec.app.tagline) : "Click through every screen, then tune it.";
    body.appendChild(el("header", { class: "p-head" }, [
      el("p", { class: "p-eyebrow", text: "Prototype" }),
      el("h1", { text: api.t(spec.app.name) }), el("p", { text: tagline })
    ]));

    body.appendChild(el("section", { class: "p-section", "aria-labelledby": "ph-look" }, [
      el("h2", { id: "ph-look", text: "Look" }), directionCards(spec),
      seg("mode", "Appearance", "The app follows the phone's setting; both palettes ship.", ["light", "dark"],
        function (v) { api.set("mode", v); })
    ]));
    body.appendChild(el("section", { class: "p-section", "aria-labelledby": "ph-feel" }, [
      el("h2", { id: "ph-feel", text: "Feel" }),
      seg("density", "Density", "Minimal to rich: spacing and row height.", CFG.density, function (v) { api.set("density", v); }),
      seg("temperature", "Temperature", "Motion, corner radius and accent saturation.", CFG.temperature, function (v) { api.set("temperature", v); }),
      seg("tone", "Copy tone", null, ["calm", "playful"], function (v) { api.set("tone", v); })
    ]));

    screenBox = el("section", { class: "p-section", "aria-labelledby": "ph-screen", "aria-live": "polite" });
    body.appendChild(screenBox);

    var feats = spec.features || [];
    if (feats.length) {
      var list = el("div", { class: "p-row" });
      feats.forEach(function (f) {
        switches[f.id] = sw(api.t(f.label), f.why ? api.t(f.why) : null, function (on) { api.setFeature(f.id, on); });
        list.appendChild(switches[f.id]);
      });
      body.appendChild(el("section", { class: "p-section", "aria-labelledby": "ph-feat" }, [
        el("h2", { id: "ph-feat", text: "Features in v1" }),
        el("p", { class: "p-hint", text: "Switch one off to see the app without it. What's on becomes v1 scope." }), list
      ]));
    }

    mapList = el("ul", { class: "p-map" });
    body.appendChild(el("section", { class: "p-section", "aria-labelledby": "ph-map" }, [
      el("h2", { id: "ph-map", text: "Screen map" }), mapList
    ]));

    annotSwitch = sw("Annotations", "Label each block with the component it becomes.", function (on) { api.toggleAnnot(on); });
    copied = el("p", { class: "p-copied", role: "status", "aria-live": "polite" });
    textarea = el("textarea", { class: "p-textarea", readonly: true, "aria-label": "Your choices as JSON", hidden: true, spellcheck: "false" });
    var copyBtn = el("button", { class: "p-btn p-btn-primary", type: "button", text: "Copy my choices" });
    copyBtn.addEventListener("click", function () { api.copyChoices(); });
    var resetBtn = el("button", { class: "p-btn", type: "button", text: "Reset" });
    resetBtn.addEventListener("click", function () { api.reset(); });
    body.appendChild(el("section", { class: "p-section", "aria-labelledby": "ph-done" }, [
      el("h2", { id: "ph-done", text: "When you're happy" }), annotSwitch,
      el("div", { class: "p-actions" }, [copyBtn, resetBtn]), copied, textarea,
      el("p", { class: "p-hint", text: "Paste the JSON back into the chat. It becomes design/choices.json." })
    ]));

    var panel = document.getElementById("panel"), handle = document.getElementById("panel-handle");
    handle.addEventListener("click", function () {
      var open = !panel.classList.contains("open");
      panel.classList.toggle("open", open);
      handle.setAttribute("aria-expanded", String(open));
    });
  }

  function buildMap(state, current) {
    mapList.textContent = "";
    var spec = api.spec, tabs = {};
    (spec.tabs || []).forEach(function (t) { tabs[t.screen] = true; });
    function item(kind, id, title, sub, isCurrent) {
      var b = el("button", { type: "button", "aria-current": isCurrent ? "true" : null }, [
        el("span", null, [el("b", { text: title }), el("small", { text: sub })]),
        el("span", { class: "p-kind", text: kind })
      ]);
      b.addEventListener("click", function () { api.jump(kind === "Sheet" ? "sheet" : "screen", id); });
      mapList.appendChild(el("li", null, [b]));
    }
    spec.screens.forEach(function (s) {
      var n = s.variants.length;
      var v = api.variantOf(s);
      var sub = (n > 1 ? api.t(v.label) + " · " + n + " layouts" : "1 layout") + (s.states && s.states.empty ? " · empty state" : "");
      item(tabs[s.id] ? "Tab" : "Screen", s.id, api.t(s.title), sub, !state.sheet && current === s.id);
    });
    (spec.sheets || []).forEach(function (sh) {
      item("Sheet", sh.id, api.t(sh.title), sh.blocks.length + " blocks", state.sheet === sh.id);
    });
  }

  function buildScreenBox(state, s) {
    screenBox.textContent = "";
    radios.variant = []; radios.state = [];
    screenBox.appendChild(el("h2", { id: "ph-screen", text: "This screen: " + api.t(s.title) }));
    if (s.variants.length > 1) {
      screenBox.appendChild(seg("variant", "Layout", "Try each; your pick is what gets built.",
        s.variants.map(function (v) { return v.id; }), function (v) { api.setVariant(s.id, v); },
        function (vid) { return api.t(s.variants.filter(function (v) { return v.id === vid; })[0].label); }));
      setRadio("variant", api.variantOf(s).id);
    } else {
      screenBox.appendChild(el("p", { class: "p-hint", text: "One layout for this screen." }));
    }
    if (s.states && s.states.empty) {
      screenBox.appendChild(seg("state", "State", "What a brand-new user sees.", ["default", "empty"],
        function (v) { api.setScreenState(s.id, v); }));
      setRadio("state", state.screenState[s.id] || "default");
    }
  }

  function sync(state, screen) {
    ["direction", "mode", "density", "temperature", "tone"].forEach(function (k) { setRadio(k, state[k]); });
    Object.keys(switches).forEach(function (fid) { switches[fid].setAttribute("aria-checked", String(!!state.features[fid])); });
    annotSwitch.setAttribute("aria-checked", String(!!state.annotations));
    paintDirections(state.mode);
    // Rebuild the per-screen box only when the screen changes, so arrow-keying
    // through layouts doesn't lose focus; otherwise just re-check its radios.
    var key = screen.id + "|" + state.tone;
    if (lastScreen !== key) {
      lastScreen = key;
      buildScreenBox(state, screen);
    } else {
      setRadio("variant", api.variantOf(screen).id);
      setRadio("state", state.screenState[screen.id] || "default");
    }
    var buttons = mapList.querySelectorAll("button");
    var focused = Array.prototype.indexOf.call(buttons, document.activeElement);
    buildMap(state, screen.id);
    if (focused >= 0) mapList.querySelectorAll("button")[focused].focus({ preventScroll: true });
  }

  function showChoices(json, ok) {
    textarea.hidden = false;
    textarea.value = json;
    copied.textContent = ok ? "Copied. It's also below if you'd rather select it yourself."
      : "Your browser blocked the clipboard. Select the text below and copy it.";
    if (!ok) { textarea.focus(); textarea.select(); }
  }

  return { build: build, sync: sync, showChoices: showChoices };
})();
