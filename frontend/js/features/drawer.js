/* features/drawer.js — Side drawer navigation. */
import { closeChat } from './chat.js';
import { syncThemeControls } from './theme.js';
import { iconSvg } from '../ui/icons.js';

export function renderDrawerNav(){
  const items = [
    ['home','Home','home', false],
    ['home','Browse Properties','building', true],
    ['verify-document','Verify Your Document','filecheck', false],
    ['ownerverify','Owner Verification System','shield', false],
    ['verlist','My Verifications','shield', false],
    ['savedlist','Saved Properties','heart', false],
    ['reportslist','Report A Scam','doc', false],
  ];
  document.getElementById('drawerNav').innerHTML = items.map(([v,label,icon,scroll])=>`
    <button class="drawer-item" onclick="${v==='verify-document'?'openVerifyDocument()':`nav('${v}')`};closeDrawer();${scroll?'scrollToGrid();':''}">
      <span class="di-icon"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${iconSvg(icon)}</svg></span>
      ${label}<span class="chev">›</span>
    </button>`).join('') + `
    <button class="drawer-item" onclick="openChat();closeDrawer();">
      <span class="di-icon"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${iconSvg('faq')}</svg></span>
      Property Assistance<span class="chev">›</span>
    </button>`;
  syncThemeControls();
}

export function openDrawer(){ document.getElementById('drawer').classList.add('open'); document.getElementById('overlayBg').classList.add('show'); }

export function closeDrawer(){ document.getElementById('drawer').classList.remove('open'); document.getElementById('overlayBg').classList.remove('show'); }

/* Called once at startup: tapping the dimmed overlay closes whichever panel is open. */
export function initDrawer(){
  document.getElementById('overlayBg').onclick = ()=>{ closeDrawer(); closeChat(); };
}
