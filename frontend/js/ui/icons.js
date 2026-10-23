/* ui/icons.js — Inline SVG icon set used by the templates. */

export function iconSvg(name){
  const icons = {
    home:'<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/>',
    building:'<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M9 8h1M14 8h1M9 12h1M14 12h1M9 16h1M14 16h1"/>',
    shield:'<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6l-7-3Z"/>',
    heart:'<path d="M12 20s-7-4.4-9.5-9C.9 7.6 3 4 6.5 4c2 0 3.5 1.2 4.5 2.7C12 5.2 13.5 4 15.5 4 19 4 21.1 7.6 19.5 11 17 15.6 12 20 12 20Z"/>',
    doc:'<path d="M8 2h6l4 4v14a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"/><path d="M14 2v4h4"/>',
    filecheck:'<path d="M8 2h6l4 4v14a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"/><path d="M14 2v4h4"/><path d="m9.2 14.3 1.8 1.8L15 12"/>',
    chart:'<path d="M4 20V10M12 20V4M20 20v-7"/>',
    faq:'<path d="M21 11.5a8.38 8.38 0 0 1-9 8.4A8.5 8.5 0 1 1 21 11.5Z"/><path d="M9.6 9.2a2.4 2.4 0 1 1 3.5 2.1c-.8.4-1.3 1-1.3 1.9"/><circle cx="11.8" cy="15.8" r=".6" fill="currentColor" stroke="none"/>'
  };
  return icons[name]||icons.home;
}
