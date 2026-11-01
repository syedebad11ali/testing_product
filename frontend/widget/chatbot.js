/* Property chatbot widget. Embed with: <script src="https://YOUR-HOST/static/chatbot.js" defer></script>
   Optional overrides: window.PropertyChatConfig = { apiUrl, title, subtitle, brandText, brandLogo, poweredBy, greeting, chips } */
(function () {
  var script = document.currentScript;
  var origin = script && script.src ? new URL(script.src).origin : "";
  var cfg = Object.assign({
    apiUrl: origin + "/api/chat",
    title: "Property Assistant",
    subtitle: "An AI assistant that can estimate property prices, compare areas and search our property records. Ask me anything about properties in Karachi!",
    brandText: "Property Assistant", brandLogo: "", poweredBy: "Gemini",
    greeting: "Hey There! 👋 How may I help you today?",
    chips: ["Estimate a house price in DHA", "Cheapest area for apartments?", "Show plots under 3 crore in Malir"]
  }, window.PropertyChatConfig || {});
  var cssHref = script && script.src ? script.src.replace(/chatbot\.js.*$/, "chatbot.css") : "/static/chatbot.css";
  var link = document.createElement("link"); link.rel = "stylesheet"; link.href = cssHref; document.head.appendChild(link);

  /* Where "Log in / Sign up" goes: ALWAYS the KPT application origin, i.e. the host this script was served from (script.src), never
     cfg.apiUrl or anything else a page can override. On the first-party site that is the same origin; with no usable script URL it is a
     relative link. Under the chosen security model an embedded widget on another site never carries the KPT session (SameSite=Lax cookies,
     no credentialed CORS), so there it can only send the visitor to KPT's own site to use the assistant. */
  var kptOrigin = /^https?:\/\//.test(origin) ? origin : "";
  var thirdParty = !!kptOrigin && kptOrigin !== window.location.origin;
  var LOGIN_NEXT = "/chatbot-demo";   // a fixed first-party page that hosts this widget; no user input is ever placed in the link
  var LOGIN_HREF = kptOrigin + "/login?next=" + encodeURIComponent(LOGIN_NEXT);
  var PASSWORD_HREF = kptOrigin + "/login?change=1";   // the existing mandatory password-change screen
  var AUTH = {
    login: { title: "Login required", text: "Create an account or log in to use this feature.", action: "Log in / Sign up", href: LOGIN_HREF },
    password: { title: "Password change required", text: "You must change your password before continuing.", action: "Change password", href: PASSWORD_HREF }
  };
  var THIRD_PARTY_NOTE = "Being logged in on this website does not sign in this embedded assistant. Log in on the Karachi Property Trust website to chat with the assistant there.";

  var KEY = "pc-state", st = load();
  function load() { try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
  function newId() { return (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()); }
  st.sid = st.sid || newId(); st.msgs = st.msgs || [];

  var I = {
    chat: '<svg class="pc-ico-chat" viewBox="0 0 24 24"><path d="M12 3.5c-4.7 0-8.5 3.3-8.5 7.4 0 2.1 1 4 2.6 5.3L5.4 20l3.9-1.9c.9.2 1.8.4 2.7.4 4.7 0 8.5-3.3 8.5-7.4S16.700 3.500 12 3.500z"/></svg>',
    x: '<svg class="pc-ico-x" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    refresh: '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/></svg>',
    mic: '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.500 11.500a6.500 6.500 0 0 0 13 0M12 18v3"/></svg>',
    up: '<svg viewBox="0 0 24 24"><path d="M12 19V5M5.500 11.500L12 5l6.500 6.500"/></svg>'
  };

  var root = document.createElement("div"); root.className = "pc-root";
  root.innerHTML =
    '<section class="pc-panel" role="dialog" aria-label="' + esc(cfg.title) + '">' +
      '<div class="pc-top"><div class="pc-brand">' + (cfg.brandLogo ? '<img alt="' + esc(cfg.brandText) + '" src="' + esc(cfg.brandLogo) + '">' : esc(cfg.brandText)) + '</div>' +
        '<div class="pc-actions"><button class="pc-btn" data-a="reset" aria-label="Start a new chat">' + I.refresh + '</button>' +
        '<button class="pc-btn" data-a="close" aria-label="Close chat">' + I.close + '</button></div></div>' +
      '<div class="pc-scroll"><div class="pc-hero"><div class="pc-orb"></div><h2 class="pc-title">' + esc(cfg.title) + '</h2>' +
        '<p class="pc-sub">' + esc(cfg.subtitle) + '</p></div><div class="pc-day">Today</div>' +
        '<div class="pc-msgs" aria-live="polite"></div><div class="pc-chips"></div></div>' +
      '<form class="pc-compose" autocomplete="off"><input class="pc-input" type="text" maxlength="1000" placeholder="Type your message..." aria-label="Type your message">' +
        '<button type="button" class="pc-btn pc-mic" aria-label="Voice input">' + I.mic + '</button>' +
        '<button type="submit" class="pc-send" aria-label="Send" disabled>' + I.up + '</button></form>' +
      '<div class="pc-foot">Powered by <b>' + esc(cfg.poweredBy) + '</b></div>' +
    '</section>' +
    '<button class="pc-launcher" aria-label="Open chat"><span class="pc-launcher-in">' + I.chat + I.x + '</span></button>';
  document.body.appendChild(root);

  var $ = function (s) { return root.querySelector(s); };
  var msgs = $(".pc-msgs"), chips = $(".pc-chips"), scroller = $(".pc-scroll"), input = $(".pc-input"),
      send = $(".pc-send"), form = $(".pc-compose"), launcher = $(".pc-launcher"), busy = false;

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function inline(s) { return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>"); }
  function md(text) {
    var out = "", list = false;
    esc(text).split("\n").forEach(function (l) {
      var m = l.match(/^\s*[-*•]\s+(.*)/);
      if (m) { if (!list) { out += "<ul>"; list = true; } out += "<li>" + inline(m[1]) + "</li>"; }
      else { if (list) { out += "</ul>"; list = false; } if (l.trim()) out += "<p>" + inline(l) + "</p>"; }
    });
    return out + (list ? "</ul>" : "");
  }
  function toBottom() { scroller.scrollTop = scroller.scrollHeight; }

  /* Authorization failures are shown as one fixed card (never the backend's wording, never an assistant bubble) and the composer is
     locked, so nothing is retried or resent until the visitor starts a new chat. */
  var locked = null, authCard = null;
  function showAuthCard(kind) {
    if (locked) return;                        // never a second prompt
    locked = kind; var a = AUTH[kind];
    authCard = document.createElement("div"); authCard.className = "pc-login"; authCard.setAttribute("role", "alert");
    var h = document.createElement("h3"); h.className = "pc-login-title"; h.textContent = a.title;
    var p = document.createElement("p"); p.className = "pc-login-text"; p.textContent = a.text;
    var l = document.createElement("a"); l.className = "pc-login-btn"; l.href = a.href; l.textContent = a.action;
    if (thirdParty) { l.target = "_blank"; l.rel = "noopener noreferrer"; }
    authCard.appendChild(h); authCard.appendChild(p);
    if (thirdParty) { var n = document.createElement("p"); n.className = "pc-login-note"; n.textContent = THIRD_PARTY_NOTE; authCard.appendChild(n); }
    authCard.appendChild(l);
    msgs.appendChild(authCard); chips.innerHTML = ""; toBottom();
    input.disabled = true; input.placeholder = a.title; syncSend();
  }
  function clearAuthLock() {
    locked = null; if (authCard) { authCard.remove(); authCard = null; }
    input.disabled = false; input.placeholder = "Type your message...";
  }
  /* Only exactly these two answers mean "not allowed to chat": 401 auth_required and 403 guest_not_allowed (login), and 403
     password_change_required (password). Every other status/code, including other 403s, keeps the ordinary error handling. */
  function authKind(status, d) {
    var code = d && d.code;
    if (status === 401 && code === "auth_required") return "login";
    if (status === 403 && code === "guest_not_allowed") return "login";
    if (status === 403 && code === "password_change_required") return "password";
    return null;
  }
  function AuthError(kind) { this.kind = kind; }

  function add(role, text, meta, retryText) {
    var row = document.createElement("div"); row.className = "pc-row " + (role === "error" ? "bot err" : role);
    var b = document.createElement("div"); b.className = "pc-bubble";
    if (role === "user") b.textContent = text; else b.innerHTML = md(text);
    row.appendChild(b);
    if (retryText) {
      var r = document.createElement("button"); r.type = "button"; r.className = "pc-retry"; r.textContent = "Try again";
      r.onclick = function () { row.remove(); st.msgs = st.msgs.filter(function (m) { return m.role !== "error"; }); ask(retryText, true); };
      b.appendChild(r);
    }
    if (meta) { var m = document.createElement("div"); m.className = "pc-meta"; m.textContent = meta; row.appendChild(m); }
    msgs.appendChild(row); toBottom(); return row;
  }
  /* The server reports which engine answered; keep the footer honest (greetings leave it unchanged). */
  var PROVIDERS = { openai: "OpenAI", gemini: "Gemini" };
  function setFoot(d) {
    var f = root.querySelector(".pc-foot"), src = d && d.source;
    if (!f) return;
    if (src === "offline") f.innerHTML = "AI service unavailable \u00b7 <b>offline mode</b>";
    else if (PROVIDERS[src]) f.innerHTML = "Powered by <b>" + esc(PROVIDERS[src]) + "</b>";
  }
  function metaFor(d) {
    if (d.source === "greeting") return "";
    if (d.source === "offline") return "Offline mode \u00b7 answered from property data";
    return d.from_data ? "From property data" : "General knowledge";
  }

  function renderChips() {
    chips.innerHTML = "";
    if (st.msgs.some(function (m) { return m.role === "user"; })) return;
    cfg.chips.forEach(function (t) {
      var c = document.createElement("button"); c.type = "button"; c.className = "pc-chip"; c.textContent = t;
      c.onclick = function () { ask(t); }; chips.appendChild(c);
    });
  }
  function render() {
    msgs.innerHTML = "";
    if (!st.msgs.length) st.msgs.push({ role: "bot", text: cfg.greeting });
    st.msgs.forEach(function (m) { add(m.role, m.text, m.meta, m.retry); });
    renderChips();
  }

  function ask(text, isRetry) {
    text = text.trim(); if (!text || busy || locked) return;
    busy = true; send.disabled = true;
    var userRow = null;
    if (!isRetry) { st.msgs.push({ role: "user", text: text }); userRow = add("user", text); }
    chips.innerHTML = ""; save();
    var t = document.createElement("div"); t.className = "pc-row bot";
    t.innerHTML = '<div class="pc-bubble pc-typing" aria-label="Assistant is typing"><i></i><i></i><i></i></div>';
    msgs.appendChild(t); toBottom();
    var ctl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 60000);
    fetch(cfg.apiUrl, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: st.sid, message: text }), signal: ctl ? ctl.signal : undefined })
      .then(function (r) {
        return r.text().then(function (raw) {
          var d = {}; try { d = raw ? JSON.parse(raw) : {}; } catch (e) {}
          var kind = !r.ok ? authKind(r.status, d) : null;
          if (kind) throw new AuthError(kind);
          if (!r.ok) throw new Error(d.error || "Server error (" + r.status + "). Please try again.");
          if (!d.reply) throw new Error("The server sent an empty reply. Please try again.");
          return d;
        });
      })
      .then(function (d) { t.remove(); setFoot(d); var meta = metaFor(d); st.msgs.push({ role: "bot", text: d.reply, meta: meta }); add("bot", d.reply, meta); })
      .catch(function (e) {
        t.remove();
        if (e instanceof AuthError) {
          // the rejected message was never answered: drop it (not kept, not resent) and show the one fixed prompt
          if (userRow) { userRow.remove(); var i = st.msgs.lastIndexOf(st.msgs.filter(function (m) { return m.role === "user" && m.text === text; }).pop()); if (i >= 0) st.msgs.splice(i, 1); }
          showAuthCard(e.kind); return;
        }
        var msg = (e && e.name === "AbortError") ? "The assistant took too long to respond. Please try again."
          : (e && e.message && e.message !== "Failed to fetch") ? e.message
          : "I couldn't reach the server. Check your connection and try again.";
        st.msgs.push({ role: "error", text: msg, retry: text }); add("error", msg, "", text);
      })
      .then(function () { clearTimeout(timer); busy = false; syncSend(); save(); if (isOpen()) input.focus(); });
  }

  function syncSend() { var ok = input.value.trim().length > 0 && !busy && !locked; send.disabled = !ok; send.classList.toggle("ready", ok); }
  function isOpen() { return root.classList.contains("pc-open"); }
  function setOpen(v) {
    root.classList.toggle("pc-open", v); launcher.setAttribute("aria-label", v ? "Close chat" : "Open chat");
    st.open = v; save(); if (v) { setTimeout(function () { toBottom(); input.focus(); }, 60); }
  }

  launcher.onclick = function () { setOpen(!isOpen()); };
  root.querySelector('[data-a="close"]').onclick = function () { setOpen(false); launcher.focus(); };
  root.querySelector('[data-a="reset"]').onclick = function () { clearAuthLock(); st.sid = newId(); st.msgs = []; save(); render(); };
  input.addEventListener("input", syncSend);
  form.addEventListener("submit", function (e) { e.preventDefault(); var v = input.value; input.value = ""; syncSend(); ask(v); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && isOpen()) setOpen(false); });

  // Voice input (browser speech recognition; hidden when unsupported)
  var mic = $(".pc-mic"), SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { mic.style.display = "none"; } else {
    var rec = new SR(), on = false; rec.lang = "en-US"; rec.interimResults = false;
    rec.onresult = function (e) { input.value = e.results[0][0].transcript; syncSend(); input.focus(); };
    rec.onend = rec.onerror = function () { on = false; mic.classList.remove("on"); };
    mic.onclick = function () { if (on) { rec.stop(); return; } try { rec.start(); on = true; mic.classList.add("on"); } catch (e) {} };
  }

  render();
  if (st.open) setOpen(true);
})();
