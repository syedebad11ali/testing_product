/* Inline-handler registry.
 *
 * Templates still use inline attributes (onclick="nav('home')"), which resolve names on
 * `window`. This is the ONE place that publishes them: every name below is imported from
 * its feature module, so nothing is implicitly global. tests/frontend/handlers.test.js
 * fails if a template references a handler that is not listed here.
 *
 * Migration path: replace attributes with data-action + one delegated listener, then delete this file. */
import { nav } from '../app/router.js';
import { closeChat, openChat } from '../features/chat.js';
import { closeDrawer, openDrawer } from '../features/drawer.js';
import { renderList, scrollToGrid, setArea, setSearch, setSort, setTypeFilter, toggleSave } from '../features/home.js';
import { checkOwnerClaim, loadOwnerVerificationData, lookupOwnerProperty, setOwnerClaim, renderOwnerForecast, setOwnerForecastYears, setOwnerPropertyId } from '../features/ownerVerification.js';
import { hidePromo } from '../features/promo.js';
import { handleDocUpload, saveManualInfo } from '../features/property.js';
import { toggleTheme } from '../features/theme.js';
import { captureDocumentFrame, closeDocumentCamera, docHandleCameraCapture, retakeDocumentCapture, startDocumentCamera, switchDocumentCamera, useCapturedDocument } from '../features/verifyDocument/camera.js';
import { docDeleteHistory, docGoStep, docHandleFile, docPickAutoType, docPickMethod, docPickType, docRemoveFile, docSetField, docStartManualCheck, docStartSample, docViewHistory, openReportEvidenceCamera, openReportEvidenceUpload, openVerifyDocument } from '../features/verifyDocument/flow.js';
import { closeNotVerifiedModal } from '../features/verifyDocument/views.js';

Object.assign(window, {
  captureDocumentFrame,
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
  openChat,
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
});
