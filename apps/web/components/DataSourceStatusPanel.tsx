import type { ConfigStatusItem } from "../lib/types";

const statusCopy: Record<ConfigStatusItem["status"], { label: string; dot: string; badge: string }> = {
  ready: {
    label: "已就绪",
    dot: "bg-emerald-500",
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  },
  missing_key: {
    label: "缺少 Key",
    dot: "bg-amber-500",
    badge: "bg-amber-50 text-amber-700 ring-amber-100",
  },
  disabled: {
    label: "未启用",
    dot: "bg-slate-300",
    badge: "bg-slate-100 text-slate-500 ring-slate-200",
  },
  local: {
    label: "本地",
    dot: "bg-sky-500",
    badge: "bg-sky-50 text-sky-700 ring-sky-100",
  },
};

export function DataSourceStatusPanel({ items }: { items: ConfigStatusItem[] }) {
  return (
    <section id="sources" className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Data Sources</p>
          <h2 className="mt-1 text-xl font-black tracking-tight text-slate-950">数据源配置状态</h2>
        </div>
        <p className="text-sm text-slate-500">只读展示，不显示 API Key 明文。</p>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => {
          const view = statusCopy[item.status];
          return (
            <article key={item.name} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${view.dot}`} aria-hidden="true" />
                    <h3 className="font-black text-slate-950">{item.name}</h3>
                  </div>
                  <p className="mt-1 text-xs font-semibold text-slate-500">{item.role}</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${view.badge}`}>
                  {view.label}
                </span>
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">{item.detail}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
