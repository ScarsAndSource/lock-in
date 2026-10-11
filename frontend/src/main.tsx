import React from 'react';
import ReactDOM from 'react-dom/client';
import { AppProvider } from './context/AppContext';
import { AppContent } from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppProvider>
      <AppContent />
    </AppProvider>
  </React.StrictMode>
);

// Register service worker if supported
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((err) => {
      console.warn('SW registration failed:', err);
    });
  });
}
