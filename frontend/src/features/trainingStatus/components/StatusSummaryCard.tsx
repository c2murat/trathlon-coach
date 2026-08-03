type Props = {
  label: string;
  value: string;
  detail: string;
  variant: "fitness" | "fatigue" | "form" | "load";
};

export function StatusSummaryCard({ label, value, detail, variant }: Props) {
  return (
    <article className={`status-summary-card status-summary-card--${variant}`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
        <path d="M4 18 9 12l4 3 7-9M4 21h16" />
      </svg>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
