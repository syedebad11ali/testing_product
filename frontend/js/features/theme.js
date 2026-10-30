/* features/theme.js — Light/dark theme toggle. */
import { writePrefs } from '../core/cookies.js';

export function syncThemeControls(){
  const isDark = document.documentElement.dataset.theme==='dark';
  const toggle = document.getElementById('themeToggle');
  if(toggle){
    toggle.setAttribute('aria-checked',String(isDark));
    toggle.setAttribute('aria-label','Switch to '+(isDark?'light':'dark')+' theme');
    toggle.title = 'Switch to '+(isDark?'light':'dark')+' theme';
  }
}

export function toggleTheme(){
  const theme = document.documentElement.dataset.theme==='dark'?'light':'dark';
  document.documentElement.dataset.theme = theme;
  writePrefs({ theme }); // cookie only with Preferences consent; otherwise remembered for this visit
  syncThemeControls();
}
