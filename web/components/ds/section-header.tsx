import { cn } from "@/lib/utils";

export function SectionHeader({
  title,
  description,
  count,
  actions,
  as: Tag = "h2",
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  count?: number;
  actions?: React.ReactNode;
  as?: "h1" | "h2" | "h3";
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-3", className)}>
      <div className="min-w-0 space-y-1">
        <Tag className={cn("flex items-baseline gap-2 font-semibold text-foreground", Tag === "h1" ? "text-[1.75rem] leading-tight tracking-[-0.02em]" : Tag === "h2" ? "text-base" : "text-sm")}>
          {title}
          {count !== undefined ? <span className="tnum text-sm font-normal text-muted-foreground">{count}</span> : null}
        </Tag>
        {description ? <p className="max-w-[70ch] text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex max-w-full min-w-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** Top of every route: title, one line of context, actions on the right. */
export function PageHeader(props: Omit<Parameters<typeof SectionHeader>[0], "as">) {
  return <SectionHeader as="h1" {...props} className={cn("mb-8", props.className)} />;
}
