/* Effects that make the prototype feel like a finished app rather than a wireframe:
   touch bloom and the commit pulse, numbers that count up, drag-to-dismiss sheets,
   and the optional WebGL "field" atmosphere. Every one checks Proto.fx.reduced()
   first and does nothing (or the static equivalent) under reduced motion. None of
   them own state: the runtime calls in, and they only ever touch the DOM. */
Proto.fx = (function () {
  "use strict";
  var phone = null, isReduced = function () { return false; };

  function init(phoneEl, reducedFn) {
    phone = phoneEl;
    isReduced = reducedFn;
    phone.addEventListener("pointerdown", bloom);
    phone.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest(".b-button.primary");
      if (b) commit(b);
    });
  }

  /* ---- touch bloom: light spreads from where the finger landed ---- */
  function bloom(e) {
    if (isReduced() || e.button > 0) return;
    var t = e.target.closest && e.target.closest(".press");
    if (!t || !phone.contains(t)) return;
    var r = t.getBoundingClientRect(), k = r.width / t.offsetWidth || 1; // the phone is CSS-scaled
    var size = Math.max(t.offsetWidth, t.offsetHeight) * 2.2;
    var dot = document.createElement("span");
    dot.className = "bloom";
    dot.setAttribute("aria-hidden", "true");
    dot.style.width = dot.style.height = size + "px";
    dot.style.left = (e.clientX - r.left) / k + "px";
    dot.style.top = (e.clientY - r.top) / k + "px";
    t.appendChild(dot);
    dot.addEventListener("animationend", function () { if (dot.parentNode) dot.parentNode.removeChild(dot); });
  }

  /* ---- commit: the primary action answers back, and the field gets a kick ---- */
  function commit(btn) {
    if (isReduced()) return;
    btn.classList.remove("pulse");
    void btn.offsetWidth;
    btn.classList.add("pulse");
    setTimeout(function () { btn.classList.remove("pulse"); }, 900);
    field.kick();
  }

  /* ---- numbers count up to their value on arrival ---- */
  var NUM = /^(\D*?)(-?\d[\d,]*(?:\.\d+)?)(.*)$/;
  function countUp(root) {
    if (isReduced()) return;
    Array.prototype.forEach.call(root.querySelectorAll(".stat-value"), function (n, idx) {
      var text = n.textContent, m = NUM.exec(text);
      if (!m) return;
      var raw = m[2].replace(/,/g, ""), target = parseFloat(raw);
      if (!isFinite(target) || target === 0) return;
      var decimals = (raw.split(".")[1] || "").length, commas = m[2].indexOf(",") >= 0;
      // Screen readers get the final value at once; the moving digits are decoration.
      n.textContent = "";
      var sr = document.createElement("span"); sr.className = "sr-only"; sr.textContent = text;
      var vis = document.createElement("span"); vis.setAttribute("aria-hidden", "true");
      n.appendChild(sr); n.appendChild(vis);
      var dur = 900, delay = 180 + idx * 70, start = null;
      function fmt(v) {
        var s = v.toFixed(decimals);
        if (commas) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        return m[1] + s + m[3];
      }
      vis.textContent = fmt(0);
      function step(ts) {
        if (!n.isConnected) return;
        if (start === null) start = ts + delay;
        var p = Math.min(1, Math.max(0, (ts - start) / dur));
        var e = 1 - Math.pow(1 - p, 4);
        vis.textContent = fmt(target * e);
        if (p < 1) requestAnimationFrame(step);
        else n.textContent = text;
      }
      requestAnimationFrame(step);
    });
  }

  /* ---- sheets: drag the grabber or header down to dismiss ---- */
  function dragToDismiss(sheet, close) {
    var handle = sheet.querySelectorAll(".sheet-grabber, .sheet-head");
    var y0 = 0, t0 = 0, dy = 0, live = false, pid = null;
    function down(e) {
      if (e.button > 0 || (e.target.closest && e.target.closest("button"))) return;
      live = true; pid = e.pointerId; y0 = e.clientY; t0 = e.timeStamp; dy = 0;
      sheet.classList.add("dragging");
      try { e.currentTarget.setPointerCapture(pid); } catch (err) { /* old browsers */ }
    }
    function move(e) {
      if (!live || e.pointerId !== pid) return;
      var k = sheet.getBoundingClientRect().height / sheet.offsetHeight || 1;
      dy = Math.max(0, (e.clientY - y0) / k);
      sheet.style.transform = "translateY(" + dy + "px)";
    }
    function up(e) {
      if (!live || e.pointerId !== pid) return;
      live = false;
      sheet.classList.remove("dragging");
      var v = dy / Math.max(1, e.timeStamp - t0);
      if (dy > 110 || (dy > 24 && v > 0.6)) close();
      sheet.style.transform = "";
    }
    Array.prototype.forEach.call(handle, function (h) {
      h.addEventListener("pointerdown", down);
      h.addEventListener("pointermove", move);
      h.addEventListener("pointerup", up);
      h.addEventListener("pointercancel", up);
    });
  }

  /* ---- the field: the glow's two lights, alive. Same geometry and the same
     contrast-capped alpha as the CSS glow (noise only ever dims a light, never
     brightens it), so text contrast holds. Falls back to the glow without WebGL. ---- */
  var field = (function () {
    var canvas = null, gl = null, prog = null, raf = 0, last = 0, t = 0, kickAt = -10, on = false, failed = false;
    var U = {};
    var VS = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
    var FS = [
      "precision mediump float;",
      "uniform vec2 res;uniform float tm,a,kick;uniform vec3 c1,c2,bg;uniform vec4 l1,l2;",
      "float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}",
      "float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);",
      " return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}",
      "float fbm(vec2 p){float s=0.,w=.5;for(int i=0;i<4;i++){s+=w*n(p);p*=2.03;w*=.5;}return s;}",
      "float lit(vec2 uv,vec4 l,float ph){",
      " vec2 c=l.xy+.03*vec2(sin(tm*.07+ph),cos(tm*.05+ph));",
      " float r=length((uv-c)/l.zw);float f=max(0.,1.-r);",
      " vec2 q=uv*vec2(2.2,4.6)+vec2(0.,-tm*.035);",
      " float w=fbm(q+fbm(q+tm*.02+kick*.6));",
      " return f*(.62+.38*w);}",
      "void main(){vec2 uv=gl_FragCoord.xy/res;uv.y=1.-uv.y;",
      " vec3 col=mix(bg,c1,a*lit(uv,l1,0.));col=mix(col,c2,a*lit(uv,l2,2.1));",
      " gl_FragColor=vec4(col,1.);}"
    ].join("\n");

    function hex(s) {
      s = (s || "").trim().replace("#", "");
      if (s.length !== 6) return [0, 0, 0];
      return [0, 2, 4].map(function (i) { return parseInt(s.substr(i, 2), 16) / 255; });
    }
    function setup() {
      if (gl || failed) return !!gl;
      canvas = phone.querySelector(".field");
      try { gl = canvas.getContext("webgl", { antialias: false, alpha: false, premultipliedAlpha: false }); } catch (e) { gl = null; }
      if (!gl) { failed = true; return false; }
      function sh(type, src) { var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; }
      prog = gl.createProgram();
      gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS));
      gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { gl = null; failed = true; return false; }
      gl.useProgram(prog);
      var buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      var loc = gl.getAttribLocation(prog, "p");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      ["res", "tm", "a", "kick", "c1", "c2", "bg", "l1", "l2"].forEach(function (k) { U[k] = gl.getUniformLocation(prog, k); });
      canvas.addEventListener("webglcontextlost", function (e) { e.preventDefault(); stop(); gl = null; failed = true; phone.classList.remove("has-field"); });
      return true;
    }
    function lights() { return Proto.CFG.atmosphere.lights; } // the same geometry the CSS glow draws
    function frame(ts) {
      raf = 0;
      if (!on || !gl) return;
      var still = isReduced() || document.hidden;
      if (!still && ts - last < 33) { raf = requestAnimationFrame(frame); return; } // ~30fps is plenty
      t += last ? Math.min(0.1, (ts - last) / 1000) : 0;
      last = ts;
      var cs = getComputedStyle(phone), w = Math.max(1, Math.round(canvas.clientWidth * 0.5)), hgt = Math.max(1, Math.round(canvas.clientHeight * 0.5));
      if (canvas.width !== w || canvas.height !== hgt) { canvas.width = w; canvas.height = hgt; gl.viewport(0, 0, w, hgt); }
      var L = lights(), k = Math.max(0, 1 - (t - kickAt) / 1.6);
      gl.uniform2f(U.res, w, hgt);
      gl.uniform1f(U.tm, t * 10);
      gl.uniform1f(U.a, parseFloat(cs.getPropertyValue("--atmo-a")) || 0);
      gl.uniform1f(U.kick, k * k);
      gl.uniform3fv(U.c1, hex(cs.getPropertyValue("--atmo-1")));
      gl.uniform3fv(U.c2, hex(cs.getPropertyValue("--atmo-2")));
      gl.uniform3fv(U.bg, hex(cs.getPropertyValue("--bg")));
      gl.uniform4fv(U.l1, L[0]);
      gl.uniform4fv(U.l2, L[1]);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (!still) raf = requestAnimationFrame(frame); // reduced motion: one still frame
    }
    function start() {
      on = true;
      if (!setup()) { phone.classList.remove("has-field"); return; }
      phone.classList.add("has-field");
      last = 0;
      if (!raf) raf = requestAnimationFrame(frame);
    }
    function stop() { on = false; if (raf) cancelAnimationFrame(raf); raf = 0; phone.classList.remove("has-field"); }
    function redraw() { if (on && gl && !raf) raf = requestAnimationFrame(frame); }
    document.addEventListener("visibilitychange", function () { if (!document.hidden) { last = 0; redraw(); } });
    return {
      set: function (wanted) { if (wanted) { start(); redraw(); } else stop(); },
      redraw: redraw,
      kick: function () { kickAt = t; redraw(); }
    };
  })();

  return { init: init, countUp: countUp, dragToDismiss: dragToDismiss, field: field, reduced: function () { return isReduced(); } };
})();
