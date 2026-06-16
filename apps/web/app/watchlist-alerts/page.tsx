"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/AdminShell";
import {
  acknowledgeWatchlistAlert,
  listWatchlistAlerts,
  muteWatchlistAlert,
  updateWatchlistStock,
} from "../../lib/api";
import type { WatchlistAlertEvent } from "../../lib/types";

type AlertFilter = "all" | "high" | "opportunity" | "plan" | "stale_review" | "handled";

const filters: Array<{ key: AlertFilter; label: string }> = [
  { key: "all", label: "全部" },
  { key: "high", label: "高危" },
  { key: "opportunity", label: "机会" },
  { key: "plan", label: "计划" },
  { key: "stale_review", label: "到期复看" },
  { key: "handled", label: "已处理" },
];

export default function WatchlistAlertsPage() {
  const [alerts, setAlerts] = useState<WatchlistAlertEvent[]>([]);
  const [filter, setFilter] = useState<AlertFilter>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [reviewText, setReviewText] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filteredAlerts = useMemo(() => alerts.filter((alert) => matchesFilter(alert, filter)), [alerts, filter]);
  const selectedAlert = alerts.find((alert) => alert.id === selectedId) ?? filteredAlerts[0] ?? null;

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    setReviewText(selectedAlert?.ai_comment ?? "");
  }, [selectedAlert?.id]);

  async function refresh() {
    try {
      const response = await listWatchlistAlerts();
      setAlerts(response.items);
      setSelectedId((current) => (current && response.items.some((item) => item.id === current) ? current : (response.items[0]?.id ?? null)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取提醒中心失败");
    }
  }

  async function handleAcknowledge(alert: WatchlistAlertEvent) {
    setBusyId(alert.id);
    setError(null);
    try {
      await acknowledgeWatchlistAlert(alert.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "标记已处理失败");
    } finally {
      setBusyId(null);
    }
  }

  async function handleMute(alert: WatchlistAlertEvent) {
    setBusyId(alert.id);
    setError(null);
    try {
      await muteWatchlistAlert(alert.id, 3);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "暂不提醒失败");
    } finally {
      setBusyId(null);
    }
  }

  async function handleSaveReview(alert: WatchlistAlertEvent) {
    const stockId = alert.stock_id;
    if (typeof stockId !== "number") {
      setError("该提醒未关联自选股，无法写入复盘结论。");
      return;
    }
    setBusyId(alert.id);
    setError(null);
    try {
      await updateWatchlistStock(stockId, { last_review_conclusion: reviewText });
      await acknowledgeWatchlistAlert(alert.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "加入复盘结论失败");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <AdminShell>
      <div className="space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Alert Center</p>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">提醒中心</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            这里集中处理自选股观察池触发的风险、机会、计划和到期复看提醒。提醒只做观察和复盘，不给交易指令。
          </p>
        </header>

        {error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-black text-slate-950">事件列表</h2>
                <p className="mt-1 text-sm text-slate-500">按优先级处理，高危提醒优先看。</p>
              </div>
              <button
                className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-bold text-slate-700"
                onClick={() => void refresh()}
                type="button"
              >
                刷新
              </button>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {filters.map((item) => (
                <button
                  key={item.key}
                  className={`rounded-xl px-3 py-2 text-sm font-bold ${
                    filter === item.key ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600"
                  }`}
                  onClick={() => setFilter(item.key)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>

            <div className="mt-4 divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-100">
              {filteredAlerts.map((alert) => (
                <button
                  key={alert.id}
                  className={`grid w-full gap-3 p-4 text-left text-sm md:grid-cols-[120px_minmax(0,1fr)_120px] ${
                    selectedAlert?.id === alert.id ? "bg-slate-50" : "bg-white hover:bg-slate-50"
                  }`}
                  onClick={() => setSelectedId(alert.id)}
                  type="button"
                >
                  <span>
                    <span className="block font-black text-slate-950">{alert.name ?? alert.symbol}</span>
                    <span className="mt-1 block text-xs text-slate-500">{alert.symbol}</span>
                  </span>
                  <span>
                    <span className="font-bold text-slate-800">{alert.trigger_reason}</span>
                    <span className="mt-1 block truncate text-xs text-slate-500">{alert.ai_comment ?? eventTypeLabel(alert.event_type)}</span>
                  </span>
                  <span className="flex items-center justify-between gap-2 md:justify-end">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${severityClass(alert.severity)}`}>
                      {severityLabel(alert.severity)}
                    </span>
                    <span className="text-xs font-semibold text-slate-500">{statusLabel(alert.status)}</span>
                  </span>
                </button>
              ))}
              {filteredAlerts.length === 0 && <p className="p-5 text-sm text-slate-500">暂无符合条件的提醒。</p>}
            </div>
          </div>

          <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-xl font-black text-slate-950">详情</h2>
            {selectedAlert ? (
              <div className="mt-4 space-y-4">
                <div className="rounded-xl bg-slate-50 p-4">
                  <div className="font-black text-slate-950">{selectedAlert.name ?? selectedAlert.symbol}</div>
                  <div className="mt-1 text-sm text-slate-500">{selectedAlert.symbol}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${severityClass(selectedAlert.severity)}`}>
                      {severityLabel(selectedAlert.severity)}
                    </span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">
                      {eventTypeLabel(selectedAlert.event_type)}
                    </span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">
                      {statusLabel(selectedAlert.status)}
                    </span>
                  </div>
                </div>

                <dl className="grid gap-3 text-sm">
                  <DetailItem label="触发原因" value={selectedAlert.trigger_reason} />
                  <DetailItem label="最近触发" value={formatDateTime(selectedAlert.last_seen_at)} />
                  <DetailItem label="数据源状态" value={JSON.stringify(selectedAlert.source_status)} />
                  <DetailItem label="规则快照" value={JSON.stringify(selectedAlert.rule_snapshot)} />
                </dl>

                <label className="block text-sm font-bold text-slate-700">
                  加入复盘结论
                  <textarea
                    className="mt-2 min-h-28 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm leading-6"
                    onChange={(event) => setReviewText(event.target.value)}
                    value={reviewText}
                  />
                </label>

                <div className="grid gap-2 sm:grid-cols-3">
                  <button
                    className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white disabled:bg-slate-300"
                    disabled={busyId === selectedAlert.id}
                    onClick={() => void handleAcknowledge(selectedAlert)}
                    type="button"
                  >
                    已处理
                  </button>
                  <button
                    className="rounded-xl bg-slate-100 px-4 py-2.5 text-sm font-bold text-slate-700 disabled:opacity-50"
                    disabled={busyId === selectedAlert.id}
                    onClick={() => void handleMute(selectedAlert)}
                    type="button"
                  >
                    暂不提醒
                  </button>
                  <button
                    className="rounded-xl bg-emerald-50 px-4 py-2.5 text-sm font-bold text-emerald-700 disabled:opacity-50"
                    disabled={busyId === selectedAlert.id || !reviewText.trim()}
                    onClick={() => void handleSaveReview(selectedAlert)}
                    type="button"
                  >
                    加入复盘结论
                  </button>
                </div>
              </div>
            ) : (
              <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">选择一条提醒查看详情。</p>
            )}
          </aside>
        </section>
      </div>
    </AdminShell>
  );
}

function matchesFilter(alert: WatchlistAlertEvent, filter: AlertFilter): boolean {
  if (filter === "all") return true;
  if (filter === "high") return alert.severity === "high";
  if (filter === "handled") return ["acknowledged", "muted", "resolved", "sent"].includes(alert.status);
  return alert.event_type === filter;
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <dt className="text-xs font-semibold text-slate-500">{label}</dt>
      <dd className="mt-1 break-words font-bold text-slate-800">{value}</dd>
    </div>
  );
}

function severityLabel(severity: WatchlistAlertEvent["severity"]) {
  return { high: "高危", medium: "关注", low: "低" }[severity];
}

function severityClass(severity: WatchlistAlertEvent["severity"]) {
  return {
    high: "bg-red-50 text-red-700 ring-1 ring-red-100",
    medium: "bg-amber-50 text-amber-700 ring-1 ring-amber-100",
    low: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",
  }[severity];
}

function eventTypeLabel(type: WatchlistAlertEvent["event_type"]) {
  return {
    risk: "风险",
    opportunity: "机会",
    plan: "计划",
    intraday: "盘中",
    stale_review: "到期复看",
  }[type];
}

function statusLabel(status: WatchlistAlertEvent["status"]) {
  return {
    active: "待处理",
    sent: "已发送",
    acknowledged: "已处理",
    muted: "暂不提醒",
    resolved: "已解决",
  }[status];
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN");
}
