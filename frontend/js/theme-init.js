/* Applies the saved theme (kpt_prefs cookie) before first paint on pages that cannot use the inline snippet in
 * index.html (login, admin, privacy). Plain blocking script. The cookie only exists if the visitor allowed
 * Preferences cookies; a missing or malformed cookie means light. */
(function () {
  var theme = 'light';
  try {
    var m = document.cookie.match(/(?:^|; )kpt_prefs=([^;]*)/);
    if (m && JSON.parse(decodeURIComponent(m[1])).theme === 'dark') theme = 'dark';
  } catch (e) { /* ignore */ }
  document.documentElement.dataset.theme = theme;
})();
