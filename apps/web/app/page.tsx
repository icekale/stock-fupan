"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../components/AdminShell";
import { DataSourceStatusPanel } from "../components/DataSourceStatusPanel";
import { ReportPreview } from "../components/ReportPreview";
import { TaskProgress } from "../components/TaskProgress";
import { WatchlistImportPanel } from "../components/WatchlistImportPanel";
import { createReport, getConfigStatus, listReports, reportAssetUrl } from "../lib/api";
import type { ConfigStatusItem, CreateReportResponse, ReportKind, ReportListItem } from "../lib/types";

export default function HomePage() {
  const [tradeDate, setTradeDate] = useState("2026-05-27");
  const [reportKind, setReportKind] = useState<ReportKind>("close");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateReportResponse | null>(null);
  const [watchlistImported, setWatchlistImported] = useState(false);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [configItems, setConfigItems] = useState<ConfigStatusItem[]>([]);

  const latestReport = reports[0];
  const readySourceCount = configItems.filter((item) => item.status === "ready" || item.status === "local").length;
  const activeStep = useMemo(() => {
    if (result) {
      return result.validation.is_valid ? 3 : 2;
    }

    return running ? 0 : 0;
  }, [result, running]);

  useEffect(() => {
    void refreshReports();
    void refreshConfigStatus();
  }, []);

  async function refreshReports() {
    try {
      const response = await listReports();
      setReports(response.items);
    } catch {
      setReports([]);
    }
  }

  async function refreshConfigStatus() {
    try {
      const response = await getConfigStatus();
      setConfigItems(response.items);
    } catch {
      setConfigItems([]);
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
      await refreshConfigStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <AdminShell>
      <div className="space-y-6">
        <header id="dashboard" className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-400">Operations Console</p>
              <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">A 股复盘后台首页</h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
                集中管理全日盘后复盘、午间复盘、历史报告与数据源状态。HTML 是核心产物，PNG 用于分享。
              </p>
            </div>
            <div className="grid grid-cols-3 gap-2 sm:min-w-[420px]">
              <SummaryMetric label="历史报告" value={`${reports.length}`} />
              <SummaryMetric label="数据源就绪" value={`${readySourceCount}/${configItems.length || 6}`} />
              <SummaryMetric label="当前模式" value={reportKind === "midday" ? "午间" : "盘后"} />
            </div>
          </div>
        </header>

        <div className="grid gap-6 xl:grid-cols-[390px_minmax(0,1fr)]">
          <aside className="space-y-6">
            <section id="generate" className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Generate</p>
                  <h2 className="mt-1 text-xl font-black text-slate-950">报告生成</h2>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">/api/reports/{reportKind}</span>
              </div>

              <label className="mt-5 block text-sm font-semibold text-slate-700" htmlFor="trade-date">
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
                <ReportKindButton active={reportKind === "close"} onClick={() => setReportKind("close")}>全日盘后复盘</ReportKindButton>
                <ReportKindButton active={reportKind === "midday"} onClick={() => setReportKind("midday")}>午间复盘</ReportKindButton>
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
          </aside>

          <section className="space-y-6">
            <DataSourceStatusPanel items={configItems} />

            <section id="reports" className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Reports</p>
                  <h2 className="mt-1 text-xl font-black text-slate-950">历史报告列表</h2>
                </div>
                <button className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-200" onClick={refreshReports} type="button">
                  刷新列表
                </button>
              </div>

              <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100">
                {reports.length > 0 ? (
                  <div className="divide-y divide-slate-100">
                    {reports.slice(0, 10).map((item) => (
                      <article key={item.id} className="grid gap-3 bg-white p-4 text-sm transition hover:bg-slate-50 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
                        <div>
                          <div className="font-black text-slate-950">
                            {item.trade_date}-{item.kind_label}
                            <span className="ml-2 text-xs font-semibold text-slate-400">{item.version}</span>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                            <span>{item.status}</span>
                            {item.created_at && <span>{new Date(item.created_at).toLocaleString("zh-CN")}</span>}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <a className="rounded-full bg-slate-950 px-3 py-1.5 text-xs font-bold text-white" href={reportAssetUrl(item.html_url)} rel="noreferrer" target="_blank">
                            查看 HTML
                          </a>
                          <a className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-700" href={reportAssetUrl(item.png_url)} rel="noreferrer" target="_blank">
                            打开 PNG
                          </a>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="bg-slate-50 p-5 text-sm text-slate-500">暂无历史报告，生成后会出现在这里。</p>
                )}
              </div>
            </section>

            <section aria-label="报告预览">
              {result ? (
                <ReportPreview result={result} />
              ) : (
                <div className="flex min-h-[360px] items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 p-8 text-center text-sm text-slate-500">
                  <div>
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-lg">沪</div>
                    <p className="font-medium text-slate-700">选择交易日后生成报告预览</p>
                    <p className="mt-1 text-slate-500">
                      {latestReport ? `最近报告：${latestReport.trade_date}-${latestReport.kind_label}` : "默认交易日为 2026-05-27。"}
                    </p>
                  </div>
                </div>
              )}
            </section>
          </section>
        </div>
      </div>
    </AdminShell>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
      <div className="text-2xl font-black tabular-nums text-slate-950">{value}</div>
      <div className="mt-1 text-xs font-semibold text-slate-500">{label}</div>
    </div>
  );
}

function ReportKindButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      className={`rounded-2xl border px-3 py-2.5 text-sm font-bold transition ${
        active ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
      }`}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  );
}
