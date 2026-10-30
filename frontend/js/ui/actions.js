/* Action registry for data-on* attributes.
 *
 * Templates use `data-onclick="nav('home')"`; ui/dispatch.js parses the attribute and calls the
 * function registered here. Nothing is published on `window`, and nothing is eval'd, so the CSP
 * can forbid inline event handlers (`script-src-attr 'none'`). tests/frontend/handlers.test.js
 * fails if a template references an action that is not listed in ACTIONS. */
import { nav } from '../app/router.js';
import { closeChat, openChat } from '../features/chat.js';
import { closeDrawer, openDrawer } from '../features/drawer.js';
import { featGo, featMove, featToggle } from '../features/featured.js';
import { openOwnerCheck } from '../features/listing.js';
import { renderList, scrollToGrid, setArea, setSearch, setSort, setTypeFilter, toggleSave } from '../features/home.js';
import { checkOwnerClaim, loadOwnerVerificationData, lookupOwnerProperty, setOwnerClaim, renderOwnerForecast, setOwnerForecastYears, setOwnerPropertyId } from '../features/ownerVerification.js';
import { hidePromo } from '../features/promo.js';
import { chatWithSeller } from '../features/sellerChat.js';
import { handleDocUpload, saveManualInfo } from '../features/property.js';
import { toggleTheme } from '../features/theme.js';
import { captureDocumentFrame, closeDocumentCamera, docHandleCameraCapture, retakeDocumentCapture, startDocumentCamera, switchDocumentCamera, useCapturedDocument } from '../features/verifyDocument/camera.js';
import { docDeleteHistory, docGoStep, docHandleFile, docPickAutoType, docPickMethod, docPickType, docRemoveFile, docSetField, docStartManualCheck, docStartSample, docViewHistory, openReportEvidenceCamera, openReportEvidenceUpload, openVerifyDocument } from '../features/verifyDocument/flow.js';
import { closeNotVerifiedModal } from '../features/verifyDocument/views.js';

export const ACTIONS = {
  captureDocumentFrame,
  chatWithSeller,
  checkOwnerClaim,
  closeChat,
  closeDocumentCamera,
  closeDrawer,
  closeNotVerifiedModal,
  docDeleteHistory,
  docGoStep,
  docHandleCameraCapture,
  docHandleFile,
  docPickAutoType,
  docPickMethod,
  docPickType,
  docRemoveFile,
  docSetField,
  docStartManualCheck,
  docStartSample,
  docViewHistory,
  handleDocUpload,
  hidePromo,
  loadOwnerVerificationData,
  lookupOwnerProperty,
  nav,
  featGo,
  featMove,
  featToggle,
  openChat,
  openOwnerCheck,
  openDrawer,
  openReportEvidenceCamera,
  openReportEvidenceUpload,
  openVerifyDocument,
  renderList,
  renderOwnerForecast,
  retakeDocumentCapture,
  saveManualInfo,
  scrollToGrid,
  setArea,
  setOwnerClaim,
  setOwnerForecastYears,
  setOwnerPropertyId,
  setSearch,
  setSort,
  setTypeFilter,
  startDocumentCamera,
  switchDocumentCamera,
  toggleSave,
  toggleTheme,
  useCapturedDocument,
  print: () => window.print(),
  toggleOpen: (id) => { const el = document.getElementById(id); if (el) el.classList.toggle('open'); },
};
