/* Entry point: wires error handling, handlers, state and the first render. */
import { ACTIONS } from './ui/actions.js';
import { installDispatcher } from './ui/dispatch.js';
import { FAVICON_URL, PROMO_DELAY_MS } from './config.js';
import { installGlobalErrorHandlers } from './core/errors.js';
import { loadDocHistory, state } from './state/store.js';
import { render, routeFromHash } from './app/router.js';
import { initDrawer } from './features/drawer.js';
import { showPromo } from './features/promo.js';
import { initAuthNav } from './features/authNav.js';
import { initHomeFilters } from './features/home.js';
import { initConsent } from './features/consent.js';
import { initDataStyles } from './ui/dataStyle.js';
import { initCreatorsMenu } from './features/creators.js';

installGlobalErrorHandlers();
installDispatcher(document, ACTIONS);
loadDocHistory();
initDrawer();
initDataStyles();
initCreatorsMenu();
initAuthNav();
initConsent();

const favicon = document.createElement('link');
favicon.rel = 'icon';
favicon.href = FAVICON_URL;
document.head.appendChild(favicon);

initHomeFilters();
routeFromHash();
window.addEventListener('hashchange', () => { if (routeFromHash()) render(); });
render();
setTimeout(showPromo, PROMO_DELAY_MS);
