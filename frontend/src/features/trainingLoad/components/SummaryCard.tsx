type SummaryIcon = "load" | "activity" | "duration" | "average";

type SummaryCardProps = {
  icon: SummaryIcon;
  label: string;
  value: string;
  detail: string;
  variant?: "primary" | "activity" | "duration" | "average";
};

function SummaryCardIcon({ icon }: { icon: SummaryIcon }) {
  const common = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (icon === "load") return <svg {...common}><path d="M13.2 2.8 5.8 13h5.3l-.5 8.2L18.2 11h-5.4l.4-8.2Z" /></svg>;
  if (icon === "activity") return <svg {...common}><circle cx="14.5" cy="4.5" r="2" /><path d="m12.8 8.2-3 4.1 3.1 2.1 2.2 4.8M12.8 8.2l3.5 2.7 3.2-.5M9.8 12.3l-3.1 5.2-3.2 1.3" /></svg>;
  if (icon === "duration") return <svg {...common}><circle cx="12" cy="13" r="8" /><path d="M9 2h6M12 5V2M17.7 7.3l1.5-1.5M12 9v4l2.8 1.8" /></svg>;
  return <svg {...common}><path d="M4 20V10h4v10M10 20V4h4v16M16 20v-7h4v7M2 20h20" /></svg>;
}

export function SummaryCard({ icon, label, value, detail, variant = "primary" }: SummaryCardProps) {
  return <div className={`training-summary-card training-summary-card--${variant}`}>
    <div className="training-summary-card__top">
      <span className="training-summary-card__icon"><SummaryCardIcon icon={icon} /></span>
      <span className="training-summary-card__label">{label}</span>
    </div>
    <strong className="training-summary-card__value">{value}</strong>
    <span className="training-summary-card__detail">{detail}</span>
  </div>;
}
