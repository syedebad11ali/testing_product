/* nice-try.js — pointer-follow tilt for the headline. Skipped when the visitor prefers reduced motion. */
(function () {
  'use strict';
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var el = document.getElementById('message');
  if (!el) return;
  window.addEventListener('pointermove', function (e) {
    var x = e.clientX / window.innerWidth - 0.5, y = e.clientY / window.innerHeight - 0.5;
    el.style.setProperty('--ry', (x * 14).toFixed(2) + 'deg');
    el.style.setProperty('--rx', (-y * 10).toFixed(2) + 'deg');
  }, { passive: true });
})();
