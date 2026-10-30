# ADR 0002: Strict `style-src`, no inline styles
Status: accepted (sessions 13-14). New code must not add `style="..."` or `<style>`; use classes, or `data-w`/`data-bg` applied through the CSSOM by `ui/dataStyle.js`. Only `/chatbot-demo` keeps `'unsafe-inline'`.
