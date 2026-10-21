import { ApiError } from "../api/client";

export function Skeleton({ height = 120 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} role="status" aria-label="Loading" />;
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const rid = error instanceof ApiError ? error.requestId : undefined;
  return (
    <div className="state error" role="alert">
      <h3>Something went wrong</h3>
      <div>{error.message}</div>
      {rid && <small className="note">Request ID: {rid}</small>}
      {onRetry && <button className="pill-btn" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="state">
      <h3>{title}</h3>
      {children && <div>{children}</div>}
    </div>
  );
}

export function NoDataset() {
  return (
    <EmptyState title="No dataset imported yet">
      Run <code>python -m app.ingestion.cli bootstrap</code> in <code>backend/</code> to import the bundled
      World Bank WDI snapshot, then reload.
    </EmptyState>
  );
}
