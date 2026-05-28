"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../components/AdminShell";
import { DataSourceStatusPanel } from "../components/DataSourceStatusPanel";
import { ReportPreview } from "../components/ReportPreview";
import { TaskProgress } from "../components/TaskProgress";
import { WatchlistImportPanel } from "../components/WatchlistImportPanel";
import { createReport, deleteReport, getConfigStatus, listReports, reportAssetUrl } from "../lib/api";
import type { ConfigStatusItem, CreateReportResponse, ReportKind, ReportListItem } from "../lib/types";

export default function HomePage() {
  const [tradeDate, setTradeDate] = useState(() => getLatestTradeDate());
  const [reportKind, setReportKind] = useState<ReportKind>("close");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateReportResponse | null>(null);
  const [watchlistImported, setWatchlistImported] = useState(false);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [deletingReportId, setDeletingReportId] = useState<number | null>(null);
  const [configItems, setConfigItems] = useState<ConfigStatusItem[]>([]);

  const latestReport = reports[0];
  const selectedReport = reports.find((item) => item.id === selectedReportId) ?? null;
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
      setSelectedReportId((currentId) => {
        if (currentId && response.items.some((item) => item.id === currentId)) {
          return currentId;
        }
        return response.items[0]?.id ?? null;
      });
    } catch {
      setReports([]);
      setSelectedReportId(null);
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

  async function handleDeleteReport(item: ReportListItem) {
    const confirmed = window.confirm(`确认删除 ${item.trade_date}-${item.kind_label} ${item.version} 吗？`);
    if (!confirmed) {
      return;
    }

    setDeletingReportId(item.id);
    setError(null);
    try {
      await deleteReport(item.id);
      if (selectedReportId === item.id) {
        setSelectedReportId(null);
      }
      setResult(null);
      await refreshReports();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeletingReportId(null);
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
                      <article
                        key={item.id}
                        className={`grid gap-3 p-4 text-sm transition lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center ${
                          selectedReportId === item.id ? "bg-slate-50 ring-1 ring-inset ring-slate-300" : "bg-white hover:bg-slate-50"
                        }`}
                      >
                        <button
                          className="text-left"
                          onClick={() => {
                            setSelectedReportId(item.id);
                            setResult(null);
                          }}
                          type="button"
                        >
                          <div className="font-black text-slate-950">
                            <span
                              className={`mr-2 inline-flex h-4 w-4 items-center justify-center rounded-full border align-[-2px] ${
                                selectedReportId === item.id ? "border-slate-950 bg-slate-950" : "border-slate-300 bg-white"
                              }`}
                            >
                              {selectedReportId === item.id && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                            </span>
                            {item.trade_date}-{item.kind_label}
                            <span className="ml-2 text-xs font-semibold text-slate-400">{item.version}</span>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                            <span>{item.status}</span>
                            {item.created_at && <span>{new Date(item.created_at).toLocaleString("zh-CN")}</span>}
                          </div>
                        </button>
                        <div className="flex flex-wrap gap-2">
                          <a className="rounded-full bg-slate-950 px-3 py-1.5 text-xs font-bold text-white" href={reportAssetUrl(item.html_url)} rel="noreferrer" target="_blank">
                            查看 HTML
                          </a>
                          <a className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-700" href={reportAssetUrl(item.png_url)} rel="noreferrer" target="_blank">
                            打开 PNG
                          </a>
                          <button
                            className="rounded-full bg-red-50 px-3 py-1.5 text-xs font-bold text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={deletingReportId === item.id}
                            onClick={() => void handleDeleteReport(item)}
                            type="button"
                          >
                            {deletingReportId === item.id ? "删除中" : "删除"}
                          </button>
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
              ) : selectedReport ? (
                <SelectedReportCard report={selectedReport} />
              ) : (
                <div className="flex min-h-[360px] items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 p-8 text-center text-sm text-slate-500">
                  <div>
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-lg">沪</div>
                    <p className="font-medium text-slate-700">选择交易日后生成报告预览</p>
                    <p className="mt-1 text-slate-500">
                      {latestReport ? `最近报告：${latestReport.trade_date}-${latestReport.kind_label}` : `默认交易日为 ${tradeDate}。`}
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

function getLatestTradeDate() {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });
  const parts = formatter.formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const date = new Date(`${values.year}-${values.month}-${values.day}T00:00:00+08:00`);
  const day = date.getDay();
  if (day === 0) {
    date.setDate(date.getDate() - 2);
  } else if (day === 6) {
    date.setDate(date.getDate() - 1);
  }
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function SelectedReportCard({ report }: { report: ReportListItem }) {
  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Selected Report</p>
      <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">
        {report.trade_date}-{report.kind_label}
        <span className="ml-2 text-sm font-semibold text-slate-400">{report.version}</span>
      </h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        已选择历史报告。HTML 是主产物，PNG 适合分享；删除会同时移除数据库记录和该版本文件夹。
      </p>
      <div className="mt-5 flex flex-wrap gap-2">
        <a className="rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white" href={reportAssetUrl(report.html_url)} rel="noreferrer" target="_blank">
          查看 HTML
        </a>
        <a className="rounded-full bg-slate-100 px-4 py-2 text-sm font-bold text-slate-700" href={reportAssetUrl(report.png_url)} rel="noreferrer" target="_blank">
          打开 PNG
        </a>
      </div>
      <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
        <InfoItem label="状态" value={report.status} />
        <InfoItem label="类型" value={report.kind_label} />
        <InfoItem label="创建时间" value={report.created_at ? new Date(report.created_at).toLocaleString("zh-CN") : "--"} />
      </dl>
    </article>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 font-bold text-slate-950">{value}</div>
    </div>
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
