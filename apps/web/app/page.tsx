"use client";

import { useMemo, useState } from "react";
import { ReportPreview } from "../components/ReportPreview";
import { Stepper } from "../components/Stepper";
import { TaskProgress } from "../components/TaskProgress";
import { createCloseReport } from "../lib/api";
import type { CreateReportResponse } from "../lib/types";

export default function HomePage() {
  const [tradeDate, setTradeDate] = useState("2026-05-26");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateReportResponse | null>(null);

  const activeStep = useMemo(() => {
    if (result) {
      return result.validation.is_valid ? 3 : 2;
    }

    return running ? 0 : 0;
  }, [result, running]);

  async function handleGenerate() {
    setRunning(true);
    setError(null);
    setResult(null);

    try {
      const response = await createCloseReport(tradeDate);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-7 flex flex-col gap-4 border-b border-slate-200 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-500">Stock Review</p>
            <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">A 股每日复盘工作台</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">v0.2 接入真实行情与新闻搜索，自动回退并展示数据源诊断。</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white/80 px-4 py-3 text-sm text-slate-600 shadow-sm">
            API：<span className="font-semibold text-slate-950">/api/reports/close</span>
          </div>
        </header>

        <Stepper activeIndex={activeStep} />

        <div className="mt-6 grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="space-y-4">
            <section className="rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-card">
              <label className="text-sm font-semibold text-slate-700" htmlFor="trade-date">
                交易日
              </label>
              <input
                id="trade-date"
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-slate-950 shadow-sm transition-colors placeholder:text-slate-400 hover:border-slate-300"
                value={tradeDate}
                onChange={(event) => setTradeDate(event.target.value)}
                placeholder="YYYY-MM-DD"
                inputMode="numeric"
              />
              <button
                className="mt-4 w-full rounded-2xl bg-slate-950 px-4 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-slate-800 active:translate-y-px disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:active:translate-y-0"
                disabled={running || tradeDate.trim().length === 0}
                onClick={handleGenerate}
                type="button"
              >
                {running ? "生成中..." : "生成收盘复盘"}
              </button>
              {error && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm leading-6 text-red-700">{error}</p>}
            </section>

            <TaskProgress running={running} completed={Boolean(result)} />
          </aside>

          <section aria-label="报告预览">
            {result ? (
              <ReportPreview result={result} />
            ) : (
              <div className="flex min-h-[540px] items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 p-8 text-center text-sm text-slate-500">
                <div>
                  <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-lg">沪</div>
                  <p className="font-medium text-slate-700">选择交易日后生成报告预览</p>
                  <p className="mt-1 text-slate-500">默认交易日为 2026-05-26。</p>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
