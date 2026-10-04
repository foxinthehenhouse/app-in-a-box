/* Prototype runtime: state, navigation (a stack per tab), sheets, toasts, per-screen
   states, variants, feature toggles, tone, persistence and "Copy my choices".
   The choices JSON it emits is exactly what `prototype.py freeze` reads. */
(function () {
  "use strict";
  var el = Proto.el, icon = Proto.icon;
  var spec = JSON.parse(document.getElementById("proto-spec").textContent);
  var D = spec.defaults;
  var screens = {}, sheets = {}, directions = {};
  spec.screens.forEach(function (s) { screens[s.id] = s; });
  (spec.sheets || []).forEach(function (s) { sheets[s.id] = s; });
  spec.directions.forEach(function (d) { directions[d.id] = d; });
  var tabIds = (spec.tabs || []).map(function (t) { return t.screen; });
  var ROOT = tabIds.length ? null : spec.screens[0].id;
  var KEY = "appbox-prototype:" + String(typeof spec.app.name === "string" ? spec.app.name : spec.app.name.calm).toLowerCase().replace(/[^a-z0-9]+/g, "-");
  // Saved clicks survive a re-render, but not a change the team made to the
  // defaults or feature list (the saved state would silently override it).
  var REV = JSON.parse(document.getElementById("proto-config").textContent).rev;
  var ALLOWED = {
    direction: Object.keys(directions), mode: ["light", "dark"], density: Proto.CFG.density,
    temperature: Proto.CFG.temperature, tone: ["calm", "playful"]
  };
  var ATMO = Proto.CFG.atmosphere;
  var ATMO_ALLOWED = { mode: ATMO.mode, intensity: ATMO.intensity, surface: ATMO.surface, grain: [true, false] };
  var reduced = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  function isReduced() { return reduced.matches || (state && state.rmPreview); }

  var phone = document.getElementById("phone"), viewport = document.getElementById("viewport");
  var tabbar = document.getElementById("tabbar"), toastHost = document.getElementById("toast-host");
  var sheetHost = document.getElementById("sheet-host"), caption = document.getElementById("stage-caption");
  var stage = document.querySelector(".stage");

  var state;
  function fresh() {
    var s = { direction: D.direction, mode: D.mode, density: D.density, temperature: D.temperature,
      tone: D.tone, variants: {}, features: {}, annotations: false, screenState: {},
      tab: tabIds[0] || "_", stacks: {}, sheet: null,
      atmosphere: atmoDefault(D.direction), atmoTouched: false, rmPreview: false };
    (spec.features || []).forEach(function (f) { s.features[f.id] = !!f["default"]; });
    tabIds.forEach(function (id) { s.stacks[id] = [id]; });
    if (ROOT) s.stacks._ = [ROOT];
    return s;
  }

  function atmoDefault(dir) {
    var d = ATMO.defaults[dir], a = {};
    Object.keys(d).forEach(function (k) { a[k] = d[k]; });
    return a;
  }

  /* ---- persistence: a convenience only, so every access is guarded ---- */
  function load() {
    var raw = null;
    try { raw = window.localStorage.getItem(KEY); } catch (e) { raw = null; }
    if (!raw) return;
    var saved;
    try { saved = JSON.parse(raw); } catch (e) { return; }
    if (!saved || typeof saved !== "object" || saved.rev !== REV) return;
    Object.keys(ALLOWED).forEach(function (k) { if (ALLOWED[k].indexOf(saved[k]) >= 0) state[k] = saved[k]; });
    Object.keys(saved.variants || {}).forEach(function (sid) {
      var s = screens[sid];
      if (s && s.variants.some(function (v) { return v.id === saved.variants[sid]; })) state.variants[sid] = saved.variants[sid];
    });
    Object.keys(saved.features || {}).forEach(function (fid) {
      if (fid in state.features && typeof saved.features[fid] === "boolean") state.features[fid] = saved.features[fid];
    });
    state.annotations = saved.annotations === true;
    state.rmPreview = saved.rmPreview === true;
    if (saved.atmoTouched === true && saved.atmosphere && typeof saved.atmosphere === "object") {
      Object.keys(ATMO_ALLOWED).forEach(function (k) {
        if (ATMO_ALLOWED[k].indexOf(saved.atmosphere[k]) >= 0) state.atmosphere[k] = saved.atmosphere[k];
      });
      state.atmoTouched = true;
    } else {
      state.atmosphere = atmoDefault(state.direction);
    }
  }
  function save() {
    try {
      var c = choices();
      c.annotations = state.annotations;
      c.rmPreview = state.rmPreview;
      c.atmoTouched = state.atmoTouched;
      c.rev = REV;
      window.localStorage.setItem(KEY, JSON.stringify(c));
    } catch (e) { /* private mode or blocked storage: the prototype still works */ }
  }

  /* ---- helpers ---- */
  function t(v) {
    if (v === null || v === undefined) return "";
    return typeof v === "string" ? v : (v[state.tone] || v.calm || "");
  }
  function variantOf(s) {
    var id = state.variants[s.id];
    return s.variants.filter(function (v) { return v.id === id; })[0] || s.variants[0];
  }
  function stack() { return state.stacks[state.tab]; }
  function current() { var st = stack(); return st[st.length - 1]; }
  function iconStyle() { return directions[state.direction].icons; }
  function ctx() { return { t: t, iconStyle: iconStyle(), act: act }; }
  function wait(ms) { return isReduced() ? 0 : ms; }
  function choices() {
    var v = {}, f = {};
    spec.screens.forEach(function (s) { v[s.id] = variantOf(s).id; });
    Object.keys(state.features).forEach(function (k) { f[k] = state.features[k]; });
    var a = {};
    Object.keys(ATMO_ALLOWED).forEach(function (k) { a[k] = state.atmosphere[k]; });
    return { direction: state.direction, mode: state.mode, density: state.density,
      temperature: state.temperature, tone: state.tone, variants: v, features: f, atmosphere: a };
  }

  function applyFeatures(root) {
    Array.prototype.forEach.call(root.querySelectorAll("[data-feature]"), function (n) {
      n.hidden = !state.features[n.getAttribute("data-feature")];
    });
    Array.prototype.forEach.call(root.querySelectorAll(".stat-grid"), function (g) {
      g.hidden = !Array.prototype.some.call(g.children, function (c) { return !c.hidden; });
    });
  }

  /* ---- phone ---- */
  function applyPhone() {
    phone.setAttribute("data-direction", state.direction);
    phone.setAttribute("data-mode", state.mode);
    phone.setAttribute("data-density", state.density);
    phone.setAttribute("data-temperature", state.temperature);
    phone.setAttribute("data-icons", iconStyle());
    phone.classList.toggle("annot", state.annotations);
    phone.classList.toggle("has-tabs", tabIds.length > 0);
    var a = state.atmosphere;
    phone.setAttribute("data-atmo", a.mode);
    phone.setAttribute("data-intensity", a.intensity);
    phone.setAttribute("data-grain", a.grain ? "on" : "off");
    phone.setAttribute("data-surface", a.surface);
    phone.classList.toggle("rm", !!isReduced());
    Proto.fx.field.set(a.mode === "field");
    Proto.fx.field.redraw();
    // the room around the phone follows its palette
    var pal = Proto.CFG.palettes[state.direction][state.mode];
    stage.setAttribute("data-mode", state.mode);
    stage.style.setProperty("--stage-glow", pal.accent);
    stage.style.setProperty("--stage-bg", state.mode === "dark" ? mix(pal.bg, "#000000", 0.45) : "");
  }
  function mix(a, b, k) { // #RRGGBB a toward b by k
    var x = parseInt(a.slice(1), 16), y = parseInt(b.slice(1), 16), out = "#";
    [16, 8, 0].forEach(function (sh) {
      var c = Math.round(((x >> sh) & 255) * (1 - k) + ((y >> sh) & 255) * k);
      out += (c < 16 ? "0" : "") + c.toString(16);
    });
    return out;
  }

  function screenBlocks(s) {
    var v = variantOf(s);
    if (state.screenState[s.id] === "empty" && s.states && s.states.empty) {
      var lead = [];
      for (var i = 0; i < v.blocks.length && v.blocks[i].type === "header"; i++) lead.push(v.blocks[i]);
      return lead.concat(s.states.empty);
    }
    return v.blocks;
  }

  function renderScreen(anim) {
    var sid = current(), s = screens[sid], st = stack();
    var old = viewport.firstChild;
    var keepScroll = !anim && old && old.getAttribute("data-screen") === sid ? old.scrollTop : 0;
    var hadFocus = phone.contains(document.activeElement);
    var layer = el("section", { class: "screen", "data-screen": sid, "aria-label": t(s.title), tabindex: "-1" });
    if (st.length > 1) {
      var backBtn = el("button", { class: "icon-btn press", type: "button", "aria-label": "Back" }, [icon("chevron", iconStyle(), "ic-back")]);
      backBtn.addEventListener("click", back);
      layer.appendChild(el("div", { class: "navbar" }, [backBtn, el("div", { class: "navbar-title t-body", text: t(s.title) }), el("span")]));
    }
    var blocks = screenBlocks(s);
    if (st.length === 1 && !blocks.some(function (b) { return b.type === "header"; })) {
      blocks = [{ type: "header", title: s.title }].concat(blocks);
    }
    var content = el("div", { class: "content" + (anim ? " enter" : "") }, Proto.renderBlocks(blocks, ctx()));
    layer.appendChild(content);
    applyFeatures(layer);
    // Overlap: the outgoing screen animates away underneath while the new one arrives.
    Array.prototype.forEach.call(viewport.querySelectorAll(".screen"), function (n) {
      if (!anim || n.classList.contains("leaving")) { n.parentNode.removeChild(n); return; }
      n.classList.add("leaving", "out-" + anim);
      n.inert = true;
      n.setAttribute("aria-hidden", "true");
      var gone = function () { if (n.parentNode) n.parentNode.removeChild(n); };
      n.addEventListener("animationend", function (e) { if (e.target === n) gone(); });
      setTimeout(gone, 1200);
    });
    viewport.appendChild(layer);
    if (keepScroll) layer.scrollTop = keepScroll;
    if (anim) layer.classList.add("in-" + anim);
    if (anim) Proto.fx.countUp(layer);
    if (anim && hadFocus) layer.focus({ preventScroll: true });
    if (anim && state.screenState[sid] !== "empty") {
      var tb = variantOf(s).blocks.filter(function (b) { return b.type === "toast" && (!b.feature || state.features[b.feature]); })[0];
      if (tb) setTimeout(function () { toast(t(tb.text)); }, wait(420));
    }
    renderTabs();
  }

  function renderTabs() {
    if (!tabIds.length) { tabbar.hidden = true; return; }
    tabbar.hidden = false;
    tabbar.textContent = "";
    (spec.tabs || []).forEach(function (tb) {
      var on = state.tab === tb.screen;
      var b = el("button", { class: "tab", type: "button", "aria-current": on ? "page" : null }, [
        el("span", { class: "tab-ic" }, [icon(tb.icon, iconStyle())]), el("span", { text: t(tb.label) })
      ]);
      b.addEventListener("click", function () { switchTab(tb.screen); });
      tabbar.appendChild(b);
    });
  }

  /* ---- navigation ---- */
  function switchTab(id) {
    if (state.tab === id && stack().length === 1) return;
    if (state.tab === id) state.stacks[id] = [id]; // tapping the active tab pops to its root
    state.tab = id;
    renderScreen("fade");
    sync();
  }
  function navigate(id) {
    if (!screens[id]) { toast("No screen called \"" + id + "\" yet"); return; }
    if (tabIds.indexOf(id) >= 0) { state.stacks[id] = [id]; state.tab = id; renderScreen("push"); sync(); return; }
    stack().push(id);
    renderScreen("push");
    sync();
  }
  function back() {
    if (stack().length < 2) return;
    stack().pop();
    renderScreen("pop");
    sync();
  }
  function jump(kind, id) {
    if (kind === "sheet") { openSheet(id); return; }
    closeSheet(true);
    var st = stack(), at = st.indexOf(id);
    if (tabIds.indexOf(id) >= 0) { state.tab = id; state.stacks[id] = [id]; }
    else if (at >= 0) st.length = at + 1;
    else st.push(id);
    renderScreen("push");
    sync();
  }
  function act(a) {
    if (!a) return;
    if (a.sheet) { openSheet(a.sheet); return; }
    var inSheet = !!state.sheet;
    if (inSheet) closeSheet();
    if (a.go) setTimeout(function () { navigate(a.go); }, inSheet ? wait(180) : 0);
    else if (a.back && !inSheet) back();
    else if (a.toast) setTimeout(function () { toast(t(a.toast)); }, inSheet ? wait(220) : 0);
  }

  /* ---- toast ---- */
  var toastTimer = null;
  function toast(text) {
    clearTimeout(toastTimer);
    toastHost.textContent = "";
    var n = el("div", { class: "toast" }, [icon("check", iconStyle()), el("span", { text: text })]);
    toastHost.appendChild(n);
    toastTimer = setTimeout(function () {
      n.classList.add("out");
      setTimeout(function () { if (n.parentNode) n.parentNode.removeChild(n); }, wait(260));
    }, 2600);
  }

  /* ---- sheets ---- */
  var sheetReturn = null;
  function sheetBody(sh) {
    return el("div", { class: "sheet-body" }, Proto.renderBlocks(sh.blocks, ctx()));
  }
  function openSheet(id) {
    var sh = sheets[id];
    if (!sh) return;
    if (!state.sheet) sheetReturn = document.activeElement;
    state.sheet = id;
    sheetHost.textContent = "";
    var scrim = el("div", { class: "scrim", "aria-hidden": "true" });
    scrim.addEventListener("click", function () { closeSheet(); });
    var close = el("button", { class: "icon-btn press", type: "button", "aria-label": "Close" }, [icon("close", iconStyle())]);
    close.addEventListener("click", function () { closeSheet(); });
    var titleId = "sheet-title-" + id;
    var dialog = el("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": titleId, tabindex: "-1" }, [
      el("div", { class: "sheet-grabber", "aria-hidden": "true" }),
      el("div", { class: "sheet-head" }, [el("h2", { class: "t-heading", id: titleId, text: t(sh.title) }), close]),
      sheetBody(sh)
    ]);
    sheetHost.appendChild(scrim);
    sheetHost.appendChild(dialog);
    applyFeatures(dialog);
    viewport.inert = true; tabbar.inert = true;
    void dialog.offsetHeight; // commit the closed position so the open state transitions
    sheetHost.classList.add("open");
    phone.classList.add("sheet-open");
    Proto.fx.dragToDismiss(dialog, function () { closeSheet(); });
    dialog.focus({ preventScroll: true });
    sync();
  }
  function closeSheet(instant) {
    if (!state.sheet) return;
    state.sheet = null;
    sheetHost.classList.remove("open");
    phone.classList.remove("sheet-open");
    viewport.inert = false; tabbar.inert = false;
    var host = sheetHost;
    setTimeout(function () { if (!state.sheet) host.textContent = ""; }, instant ? 0 : wait(380));
    if (sheetReturn && document.body.contains(sheetReturn)) sheetReturn.focus({ preventScroll: true });
    sheetReturn = null;
    sync();
  }
  function rerenderSheet() {
    if (!state.sheet) return;
    var dialog = sheetHost.querySelector(".sheet");
    var bodyNode = dialog.querySelector(".sheet-body");
    var fresh_ = sheetBody(sheets[state.sheet]);
    dialog.replaceChild(fresh_, bodyNode);
    dialog.querySelector(".sheet-head h2").textContent = t(sheets[state.sheet].title);
    applyFeatures(dialog);
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && state.sheet) { e.preventDefault(); closeSheet(); }
  });

  /* ---- panel wiring ---- */
  function sync() {
    var s = screens[current()], v = variantOf(s);
    caption.textContent = "";
    caption.appendChild(el("b", { text: t(s.title) }));
    caption.appendChild(document.createTextNode(
      (s.variants.length > 1 ? " · " + t(v.label) + " layout" : "") +
      (state.screenState[s.id] === "empty" ? " · empty state" : "") +
      (state.sheet ? " · sheet: " + t(sheets[state.sheet].title) : "")));
    Proto.panel.sync(state, s);
  }
  function refresh() {
    applyPhone();
    renderScreen(null);
    rerenderSheet();
    save();
    sync();
  }
  var api = {
    spec: spec, t: t, variantOf: variantOf,
    set: function (k, v) {
      if (ALLOWED[k].indexOf(v) < 0) return;
      state[k] = v;
      // Until the founder turns an atmosphere knob, each direction brings its own.
      if (k === "direction" && !state.atmoTouched) state.atmosphere = atmoDefault(v);
      refresh();
    },
    setVariant: function (sid, vid) { state.variants[sid] = vid; refresh(); },
    setScreenState: function (sid, st) { state.screenState[sid] = st; refresh(); },
    setFeature: function (fid, on) { state.features[fid] = on; refresh(); },
    toggleAnnot: function (on) { state.annotations = on; refresh(); },
    setAtmo: function (k, v) {
      if (!ATMO_ALLOWED[k] || ATMO_ALLOWED[k].indexOf(v) < 0) return;
      state.atmosphere[k] = v; state.atmoTouched = true; refresh();
    },
    setPreviewRM: function (on) { state.rmPreview = on; refresh(); },
    jump: jump,
    copyChoices: function () {
      var json = JSON.stringify(choices(), null, 2);
      try {
        navigator.clipboard.writeText(json).then(function () { Proto.panel.showChoices(json, true); },
          function () { Proto.panel.showChoices(json, false); });
      } catch (e) { Proto.panel.showChoices(json, false); }
    },
    reset: function () {
      try { window.localStorage.removeItem(KEY); } catch (e) { /* ignore */ }
      closeSheet(true);
      state = fresh();
      refresh();
    }
  };

  /* ---- fit the phone to the window on wide screens ---- */
  function fit() {
    var s = 1;
    if (window.innerWidth > 900) {
      var stage = document.querySelector(".stage");
      s = Math.min(1, (window.innerHeight - 90) / 844, (stage.clientWidth - 48) / 390);
      s = Math.max(0.5, s);
    }
    document.documentElement.style.setProperty("--phone-scale", String(s));
  }
  window.addEventListener("resize", fit);

  state = fresh();
  load();
  Proto.fx.init(phone, isReduced);
  if (reduced.addEventListener) reduced.addEventListener("change", function () { applyPhone(); });
  Proto.panel.build(api);
  fit();
  applyPhone();
  renderScreen("fade");
  sync();
  window.__proto = { state: function () { return state; }, choices: choices, act: act };
})();
