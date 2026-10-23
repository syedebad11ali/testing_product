/* Error types, reporting and a minimal toast.
 * `reportError` logs with context and tells the user something went wrong — use it in
 * every catch that cannot recover silently. */
export class AppError extends Error {
  constructor(message, { code = 'app_error', cause } = {}) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    if (cause) this.cause = cause;
  }
}

export function showToast(message, { timeoutMs = 6000 } = {}) {
  if (typeof document === 'undefined' || !document.body) return;
  let host = document.getElementById('kptToasts');
  if (!host) {
    host = document.createElement('div');
    host.id = 'kptToasts';
    host.className = 'kpt-toasts';
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'polite');
    document.body.appendChild(host);
  }
  const toast = document.createElement('div');
  toast.className = 'kpt-toast';
  toast.textContent = message;
  host.appendChild(toast);
  setTimeout(() => toast.remove(), timeoutMs);
}

export function reportError(error, context = '', { notify = true } = {}) {
  console.error(`[kpt]${context ? ' ' + context : ''}`, error);
  if (notify) showToast('Something went wrong. Please try again.');
}

export function installGlobalErrorHandlers() {
  window.addEventListener('error', (e) => reportError(e.error || e.message, 'uncaught'));
  window.addEventListener('unhandledrejection', (e) => reportError(e.reason, 'unhandled promise'));
}
