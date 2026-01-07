import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

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
