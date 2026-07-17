import type { SyncStatus } from "../../types/api";

interface SyncControlsProps {
  connected: boolean;
  backendOnline: boolean;
  connectUrl: string;
  status: SyncStatus;
  busy: boolean;
  onSynchronize(): void;
}

const activeStatuses: SyncStatus[] = [
  "queued",
  "running",
  "retry_scheduled",
];

export function SyncControls({
  connected,
  backendOnline,
  connectUrl,
  status,
  busy,
  onSynchronize,
}: SyncControlsProps) {
  if (!backendOnline) {
    return (
      <button className="button button--primary" type="button" disabled>
        Backend sin conexión
      </button>
    );
  }
  if (!connected) {
    return (
      <a className="button button--primary" href={connectUrl}>
        Conectar Strava
      </a>
    );
  }
  const disabled = busy || activeStatuses.includes(status);
  return (
    <button
      className="button button--primary"
      type="button"
      disabled={disabled}
      onClick={onSynchronize}
    >
      {status === "retry_scheduled"
        ? "Reanudar sincronización"
        : disabled
          ? "Sincronizando…"
          : "Sincronizar actividades"}
    </button>
  );
}

