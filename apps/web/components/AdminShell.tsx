import type { ReactNode } from "react";

const navItems = [
  { label: "概览", hint: "Dashboard" },
  { label: "报告生成", hint: "Generate" },
  { label: "历史报告", hint: "Reports" },
  { label: "数据源状态", hint: "Sources" },
  { label: "自选股导入", hint: "Watchlist" },
];

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-screen bg-slate-100 text-slate-950">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-slate-950 px-5 py-6 text-white md:block">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
            <div className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-400">Stock Review</div>
            <div className="mt-3 text-2xl font-black tracking-tight">A 股复盘后台</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">本地生成 · 真实数据优先 · HTML/PNG 分享</div>
          </div>

          <nav className="mt-6 space-y-1" aria-label="后台菜单">
            {navItems.map((item, index) => (
              <a
                key={item.label}
                className={`group flex items-center justify-between rounded-2xl px-4 py-3 text-sm transition ${
                  index === 0 ? "bg-white text-slate-950 shadow-sm" : "text-slate-300 hover:bg-white/10 hover:text-white"
                }`}
                href={`#${item.hint.toLowerCase()}`}
              >
                <span className="font-bold">{item.label}</span>
                <span className={`text-xs ${index === 0 ? "text-slate-500" : "text-slate-500 group-hover:text-slate-300"}`}>
                  {item.hint}
                </span>
              </a>
            ))}
          </nav>

          <div className="mt-8 rounded-3xl border border-white/10 bg-white/5 p-4 text-xs leading-6 text-slate-400">
            数据源优先级：TickFlow + Anspire 为主源，同花顺 / 东方财富作为复盘辅助。
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
            <div className="mb-5 flex items-center justify-between rounded-3xl border border-slate-200 bg-white px-4 py-3 shadow-sm md:hidden">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Stock Review</div>
                <div className="mt-1 text-lg font-black">A 股复盘后台</div>
              </div>
              <span className="rounded-full bg-slate-950 px-3 py-1.5 text-xs font-bold text-white">Local</span>
            </div>
            {children}
          </div>
        </section>
      </div>
    </main>
  );
}
