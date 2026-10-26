/**
 * Frontend error reporting (Sentry). Does nothing, and downloads nothing, unless VITE_SENTRY_DSN was set at build time:
 * the SDK is loaded with a dynamic import after the app has started, in its own chunk.
 *
 * People write journals and urge notes here, so the SDK is told to keep that out: no breadcrumbs (clicks, console, network),
 * no user identity, no query string or #fragment on the page URL (a magic-link fragment carries a session token), and no
 * network errors (they are expected on bad signal and are handled by the offline queue).
 */
type SentryModule = typeof import('@sentry/browser');
let sentry: SentryModule | null = null;

function cleanUrl(url: string): string {
  return url.split('#')[0].split('?')[0];
}

export function initMonitoring(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;
  void import('@sentry/browser')
    .then((S) => {
      S.init({
        dsn,
        environment: import.meta.env.MODE,
        release: import.meta.env.VITE_BUILD_ID || undefined,
        sendDefaultPii: false,
        maxBreadcrumbs: 0,
        beforeBreadcrumb: () => null,
        tracesSampleRate: 0,
        ignoreErrors: ['ResizeObserver loop', 'Failed to fetch', 'Load failed', 'NetworkError', 'signal is aborted'],
        beforeSend(event) {
          delete event.user;
          delete event.breadcrumbs;
          if (event.request) {
            delete event.request.headers;
            delete event.request.cookies;
            delete event.request.data;
            delete event.request.query_string;
            if (event.request.url) event.request.url = cleanUrl(event.request.url);
          }
          return event;
        },
      });
      sentry = S;
    })
    .catch(() => {
      /* monitoring must never break the app */
    });
}

/** A handled-but-worth-knowing event (for example an offline entry the server refused). Counts and codes only: never user text. */
export function reportEvent(message: string, extra?: Record<string, string | number>): void {
  sentry?.captureMessage(message, { level: 'warning', extra });
}
