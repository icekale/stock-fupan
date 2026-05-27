"use client";

import { useEffect, useMemo, useState } from "react";
import { ReportPreview } from "../components/ReportPreview";
import { Stepper } from "../components/Stepper";
import { TaskProgress } from "../components/TaskProgress";
import { WatchlistImportPanel } from "../components/WatchlistImportPanel";
import { createReport, listReports, reportAssetUrl } from "../lib/api";
import type { CreateReportResponse, ReportKind, ReportListItem } from "../lib/types";

export default function HomePage() {
  const [tradeDate, setTradeDate] = useState("2026-05-27");
  const [reportKind, setReportKind] = useState<ReportKind>("close");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateReportResponse | null>(null);
  const [watchlistImported, setWatchlistImported] = useState(false);
  const [reports, setReports] = useState<ReportListItem[]>([]);

  const activeStep = useMemo(() => {
    if (result) {
      return result.validation.is_valid ? 3 : 2;
    }

    return running ? 0 : 0;
  }, [result, running]);

  useEffect(() => {
    void refreshReports();
  }, []);

  async function refreshReports() {
    try {
      const response = await listReports();
      setReports(response.items);
    } catch {
      setReports([]);
    }
  }

  async function handleGenerate() {
    setRunning(true);
    setError(null);
    setResult(null);

    try {
      const response = await createReport(tradeDate, reportKind);
      setResult(response);
      await refreshReports();
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
            <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">A 股复盘后台</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">支持全日盘后复盘与午间复盘，主源使用 TickFlow + Anspire，辅助源使用同花顺 / 东方财富。</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white/80 px-4 py-3 text-sm text-slate-600 shadow-sm">
            API：<span className="font-semibold text-slate-950">/api/reports/{reportKind}</span>
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
              <div className="mt-4 grid grid-cols-2 gap-2">
                <button
                  className={`rounded-2xl border px-3 py-2.5 text-sm font-bold transition ${
                    reportKind === "close"
                      ? "border-slate-950 bg-slate-950 text-white"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                  }`}
                  onClick={() => setReportKind("close")}
                  type="button"
                >
                  全日盘后复盘
                </button>
                <button
                  className={`rounded-2xl border px-3 py-2.5 text-sm font-bold transition ${
                    reportKind === "midday"
                      ? "border-slate-950 bg-slate-950 text-white"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                  }`}
                  onClick={() => setReportKind("midday")}
                  type="button"
                >
                  午间复盘
                </button>
              </div>
              <button
                className="mt-4 w-full rounded-2xl bg-slate-950 px-4 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-slate-800 active:translate-y-px disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:active:translate-y-0"
                disabled={running || tradeDate.trim().length === 0}
                onClick={handleGenerate}
                type="button"
              >
                {running ? "生成中..." : `生成${reportKind === "midday" ? "午间复盘" : "全日盘后复盘"}`}
              </button>
              {error && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm leading-6 text-red-700">{error}</p>}
            </section>

            <TaskProgress running={running} completed={Boolean(result)} />
            <WatchlistImportPanel onImported={() => setWatchlistImported(true)} />
            {watchlistImported && (
              <p className="rounded-2xl bg-emerald-50 p-3 text-sm text-emerald-700">
                自选股已导入，下一次生成报告会带入观察模块。
              </p>
            )}
            <section className="rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-card">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-bold text-slate-950">历史报告</h2>
                <button className="text-xs font-semibold text-slate-500 hover:text-slate-900" onClick={refreshReports} type="button">
                  刷新
                </button>
              </div>
              <div className="mt-4 space-y-2">
                {reports.slice(0, 8).map((item) => (
                  <div key={item.id} className="rounded-2xl bg-slate-50 p-3 text-sm">
                    <div className="font-bold text-slate-900">
                      {item.trade_date}-{item.kind_label}
                      <span className="ml-2 text-xs font-semibold text-slate-400">{item.version}</span>
                    </div>
                    <div className="mt-2 flex gap-2">
                      <a className="font-semibold text-slate-700 hover:text-slate-950" href={reportAssetUrl(item.html_url)} rel="noreferrer" target="_blank">
                        HTML
                      </a>
                      <a className="font-semibold text-slate-700 hover:text-slate-950" href={reportAssetUrl(item.png_url)} rel="noreferrer" target="_blank">
                        PNG
                      </a>
                    </div>
                  </div>
                ))}
                {reports.length === 0 && <p className="text-sm text-slate-500">暂无历史报告，生成后会出现在这里。</p>}
              </div>
            </section>
          </aside>

          <section aria-label="报告预览">
            {result ? (
              <ReportPreview result={result} />
            ) : (
              <div className="flex min-h-[540px] items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 p-8 text-center text-sm text-slate-500">
                <div>
                  <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-lg">沪</div>
                  <p className="font-medium text-slate-700">选择交易日后生成报告预览</p>
                  <p className="mt-1 text-slate-500">默认交易日为 2026-05-27。</p>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
