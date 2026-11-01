/* Runtime configuration — the only module that reads window-level settings.
 *
 * Override before this script loads, e.g. when the chat API is hosted elsewhere:
 *   <script>window.KPT_CONFIG = { chatApiUrl: 'https://api.example.com/api/v1/chat' };</script>
 * (the legacy `window.KPT_CHAT_API_URL` is still honoured).
 * Nothing secret ever belongs here: this file is shipped to every browser. */
const runtime = (typeof window !== 'undefined' && window.KPT_CONFIG) || {};
const legacyChatUrl = typeof window !== 'undefined' ? window.KPT_CHAT_API_URL : undefined;

export const CHAT_API_URL = runtime.chatApiUrl || legacyChatUrl || '/api/v1/chat';
export const VERIFY_API_URL = runtime.verifyApiUrl || '/api/v1/verification/check';
export const CHAT_TIMEOUT_MS = runtime.chatTimeoutMs || 30000;

export const LOGO_URL = 'assets/logo-icon.png';
export const FAVICON_URL = 'assets/logo-icon-trim.png';
export const SAMPLES_URL = 'assets/samples/';

/* Browser storage keys (UI preferences live in the kpt_prefs cookie, see core/cookies.js). */
export const STORAGE_KEYS = {
  docHistory: 'kpt_doc_history',
  favoriteProperties: 'kpt_favorite_properties',   // LEGACY (pre-G5.2 global favorites): only ever deleted, never read
  chat: 'kpt-property-assistant',
  bannerClosedAt: 'lastBannerClosedAt',
};

export const CHAT_STARTERS = ['Prices in Gulshan', 'Show 3 plots under 3 crore', 'Compare DHA and Clifton', 'How does verification work?'];
export const CHAT_FEEDBACK_URL = runtime.chatFeedbackUrl || '/api/v1/chat/feedback';
export const BANNER_COOLDOWN_MS = 18000; // 15-20s cooldown after a manual dismiss
export const PROMO_DELAY_MS = 2200;
