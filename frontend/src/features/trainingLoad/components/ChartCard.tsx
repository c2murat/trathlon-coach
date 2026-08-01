import type { ReactNode } from "react";

type ChartCardProps = {
  title: string;
  description: string;
  children: ReactNode;
};

export function ChartCard({
  title,
  description,
  children,
}: ChartCardProps) {
  return (
    <section className="training-chart-card">
      <header className="training-chart-card__header">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>

        <span className="training-chart-card__legend">
          <span aria-hidden="true" />
          Carga
        </span>
      </header>

      {children}
    </section>
  );
}