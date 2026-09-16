import type { ReactNode } from "react";

import { AppIcon, type AppIconName } from "./AppIcon";

type PageHeaderProps = {
  icon: AppIconName;
  eyebrow: string;
  title: string;
  description?: string;
  breadcrumb?: string | string[];
  action?: ReactNode;
};

export function PageHeader({ icon, eyebrow, title, description, breadcrumb, action }: PageHeaderProps) {
  const crumbs = breadcrumb ? (Array.isArray(breadcrumb) ? breadcrumb : [breadcrumb]) : [];

  return (
    <header className="flex flex-col gap-5 border-b border-line pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {crumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-2 text-xs font-medium text-slate">
            {crumbs.map((crumb, index) => (
              <span className="flex items-center gap-2" key={`${crumb}-${index}`}>
                {index > 0 && <span aria-hidden="true">/</span>}
                <span className={index === crumbs.length - 1 ? "text-emerald" : undefined}>{crumb}</span>
              </span>
            ))}
          </nav>
        )}
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-warm-green text-emerald">
            <AppIcon label={title} name={icon} size={20} />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-emerald">{eyebrow}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-graphite sm:text-3xl">{title}</h1>
            {description && <p className="mt-2 max-w-2xl text-sm leading-6 text-slate">{description}</p>}
          </div>
        </div>
      </div>
      {action && <div className="flex shrink-0 items-center gap-3">{action}</div>}
    </header>
  );
}
