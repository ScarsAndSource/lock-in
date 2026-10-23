// Shared class strings for the growth screens, built only from tokens the app already uses.
export const CLS = {
  card: 'bg-surface rounded-xl p-4 border border-line space-y-3',
  primary:
    'h-11 px-4 bg-ink text-ground-chalk rounded-xl font-body-strong text-body-strong disabled:opacity-40 transition-colors',
  ghost:
    'h-10 px-3 bg-surface border border-line rounded-xl font-small-medium text-small-medium text-ink disabled:opacity-40',
  input: 'w-full h-11 px-3 bg-surface border border-line rounded-xl font-small text-small text-ink',
  area: 'w-full p-3 bg-surface border border-line rounded-xl font-small text-small text-ink resize-none',
  label: 'font-caption text-caption text-muted-text uppercase tracking-wider block',
  muted: 'font-small text-small text-muted-text',
} as const;
