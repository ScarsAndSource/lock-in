import React from 'react';
import ReactDOM from 'react-dom/client';
import { AppProvider } from './context/AppContext';
import { CrewProvider } from './context/CrewContext';
import { MarutiProvider } from './components/maruti/MarutiContext';
import { AppContent } from './App';
import { startAuth } from './api/auth';
import './index.css';

// Adopt a session from an email-confirmation / magic link and register token refresh BEFORE anything renders.
startAuth();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppProvider>
      <CrewProvider>
        <MarutiProvider>
          <AppContent />
        </MarutiProvider>
      </CrewProvider>
    </AppProvider>
  </React.StrictMode>
);

// Register service worker if supported
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { updateViaCache: 'none' })
      .then((reg) => {
        // An installed PWA can stay open for days: re-check for a new build whenever it comes back to the foreground.
        document.addEventListener('visibilitychange', () => {
          if (document.visibilityState === 'visible') reg.update().catch(() => {});
        });
      })
      .catch((err) => {
        console.warn('SW registration failed:', err);
      });
  });
}
