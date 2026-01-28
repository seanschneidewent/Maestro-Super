import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// iOS Safari viewport fix: scroll to 1px to force viewport recalculation
// This fixes the bottom gap that appears on initial load but disappears after rotation
if (/iPhone|iPad|iPod/.test(navigator.userAgent)) {
  window.addEventListener('load', () => {
    // Make body 1px taller so there's something to scroll to
    document.body.style.minHeight = 'calc(100dvh + 1px)';
    requestAnimationFrame(() => {
      window.scrollTo(0, 1);
    });
  });
}

// Prevent Vite HMR from triggering full page reload on tab switch
if (import.meta.hot) {
  import.meta.hot.on('vite:beforeFullReload', () => {
    throw new Error('[HMR] Preventing full reload on reconnection');
  });
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error("Could not find root element to mount to");
}

const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
