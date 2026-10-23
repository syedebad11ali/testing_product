/* Entry point: wires error handling, handlers, state and the first render. */
import './ui/actions.js';
import { FAVICON_URL, PROMO_DELAY_MS } from './config.js';
import { installGlobalErrorHandlers } from './core/errors.js';
import { loadDocHistory, state } from './state/store.js';
import { render } from './app/router.js';
import { initDrawer } from './features/drawer.js';
import { showPromo } from './features/promo.js';

installGlobalErrorHandlers();
loadDocHistory();
initDrawer();

const favicon = document.createElement('link');
favicon.rel = 'icon';
favicon.href = FAVICON_URL;
document.head.appendChild(favicon);

if (window.location.hash === '#owner-verification') state.view = 'ownerverify';
render();
setTimeout(showPromo, PROMO_DELAY_MS);
