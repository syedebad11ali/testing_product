/* Entry point: wires error handling, handlers, state and the first render. */
import { ACTIONS } from './ui/actions.js';
import { installDispatcher } from './ui/dispatch.js';
import { FAVICON_URL, PROMO_DELAY_MS } from './config.js';
import { installGlobalErrorHandlers } from './core/errors.js';
import { loadDocHistory, state } from './state/store.js';
import { render, routeFromHash } from './app/router.js';
import { guestBlockedView, loadSessionUser } from './services/sessionUser.js';
import { initDrawer } from './features/drawer.js';
import { showPromo } from './features/promo.js';
import { initAuthNav } from './features/authNav.js';
import { initHomeFilters } from './features/home.js';
import { ensureFavoritesLoaded, refreshFavoriteControls } from './features/favorites.js';
import { initConsent } from './features/consent.js';
import { initDataStyles } from './ui/dataStyle.js';
import { initCreatorsMenu } from './features/creators.js';

installGlobalErrorHandlers();
installDispatcher(document, ACTIONS);
const docHistoryLoaded = loadDocHistory();   // G6.1b: the signed-in account's own history only, after /auth/me answers
initDrawer();
initDataStyles();
initCreatorsMenu();
initAuthNav();
initConsent();

const favicon = document.createElement('link');
favicon.rel = 'icon';
favicon.href = FAVICON_URL;
document.head.appendChild(favicon);

const homeFiltersRestored = initHomeFilters();   // G5.3b: restored for an account session only, after /auth/me answers
const firstRoute = routeFromHash();   // open views are applied synchronously; account-only ones resolve after the session check
window.addEventListener('hashchange', () => { routeFromHash().then((applied) => { if (applied) render(); }); });
render();
ensureFavoritesLoaded().then((ready) => { if (ready) { refreshFavoriteControls(); if (state.view === 'savedlist') render(); } else if (state.view === 'savedlist') render(); });   // G5.2: the signed-in account's favorites
homeFiltersRestored.then((restored) => { if (restored) render(); });
docHistoryLoaded.then((loaded) => { if (loaded && state.view === 'verify-document') render(); });
loadSessionUser().then(() => { if (state.view === 'detail') render(); });   // G6.2a-3: an account's owner card appears once the (cached) session answer arrives
firstRoute.then((applied) => { if (applied && guestBlockedView(state.view)) render(); });
setTimeout(showPromo, PROMO_DELAY_MS);
