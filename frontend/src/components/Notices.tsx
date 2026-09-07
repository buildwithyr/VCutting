import type { Notice } from '../lib/toolCalc';

const TITLES: Record<Notice['severity'], string> = {
  error: 'Fehler',
  warning: 'Warnung',
  info: 'Hinweis',
};

export function Notices({ notices, title }: { notices: Notice[]; title?: string }) {
  if (notices.length === 0) return null;
  return (
    <div className="notices">
      {title ? <h3 className="notices__title">{title}</h3> : null}
      <ul>
        {notices.map((notice, index) => (
          <li
            key={`${notice.field}-${index}`}
            className={`notice notice--${notice.severity}`}
            role={notice.severity === 'error' ? 'alert' : undefined}
          >
            <strong>{TITLES[notice.severity]}:</strong> {notice.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div className="banner banner--error" role="alert">
      <span>{message}</span>
      {onDismiss ? (
        <button type="button" onClick={onDismiss} aria-label="Meldung schliessen">
          Schliessen
        </button>
      ) : null}
    </div>
  );
}
