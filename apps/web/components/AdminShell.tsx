"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navItems = [
  { label: "首页", hint: "Home", href: "/" },
  { label: "早盘模型", hint: "Auction", href: "/morning-auction" },
  { label: "自选股", hint: "Watchlist", href: "/watchlist" },
  { label: "提醒中心", hint: "Alerts", href: "/watchlist-alerts" },
  { label: "设置", hint: "Settings", href: "/settings" },
];

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <main className="min-h-screen bg-slate-100 text-slate-950">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-slate-950 px-5 py-6 text-white md:block">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <div className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-400">Stock Review</div>
            <div className="mt-3 text-2xl font-black tracking-tight">A 股观察系统</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">独立选股 · 自选股池 · 提醒中心</div>
          </div>

          <nav className="mt-6 space-y-1" aria-label="后台菜单">
            {navItems.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  className={`group flex items-center justify-between rounded-xl px-4 py-3 text-sm transition ${
                    active ? "bg-white text-slate-950 shadow-sm" : "text-slate-300 hover:bg-white/10 hover:text-white"
                  }`}
                  href={item.href}
                >
                  <span className="font-bold">{item.label}</span>
                  <span className={`text-xs ${active ? "text-slate-500" : "text-slate-500 group-hover:text-slate-300"}`}>
                    {item.hint}
                  </span>
                </Link>
              );
            })}
          </nav>

          <div className="mt-8 rounded-2xl border border-white/10 bg-white/5 p-4 text-xs leading-6 text-slate-400">
            数据源透明化、结果可追溯、观察池可复盘，是这套系统的三条主线。
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
            <div className="mb-5 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm md:hidden">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Stock Review</div>
                  <div className="mt-1 text-lg font-black">A 股观察系统</div>
                </div>
                <span className="rounded-full bg-slate-950 px-3 py-1.5 text-xs font-bold text-white">Local</span>
              </div>
              <div className="mt-3 grid grid-cols-5 gap-1">
                {navItems.map((item) => {
                  const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      className={`rounded-lg px-2 py-2 text-center text-xs font-bold ${
                        active ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600"
                      }`}
                      href={item.href}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
            {children}
          </div>
        </section>
      </div>
    </main>
  );
}
