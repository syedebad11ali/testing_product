# ADR 0001: Plain ES modules, no build step
Status: accepted (existing design). The frontend is static HTML/CSS and native ES modules tested with `node --test`; the Flask app serves it. Consequence: no bundler or minifier, so third-party scripts (Tesseract, PDF.js) come from CDNs until self-hosted, and every file served must be CSP-compatible.
