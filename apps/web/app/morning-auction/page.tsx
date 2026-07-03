"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/AdminShell";
import {
  listMorningAuctionTrials,
  predictMorningAuction,
  saveMorningAuctionTrial,
} from "../../lib/api";
import { getLatestTradeDate } from "../../lib/tradeDate";
import type {
  MorningAuctionPredictionItem,
  MorningAuctionRun,
  MorningAuctionTrialEntry,
} from "../../lib/types";

type TrialDraft = {
  id?: string | null;
  trade_date: string;
  symbol: string;
  name: string;
  rank: string;
  prob_3pct: string;
  mode: string;
  planned_capital: string;
  entry_price: string;
  shares: string;
  entry_time: string;
  guard_time: string;
  guard_price: string;
  guard_triggered: string;
  exit_price: string;
  exit_time: string;
  status: string;
  notes: string;
};

const emptyDraft: TrialDraft = {
  trade_date: "",
  symbol: "",
  name: "",
  rank: "",
  prob_3pct: "",
  mode: "live_small",
  planned_capital: "",
  entry_price: "",
  shares: "",
  entry_time: "",
  guard_time: "10:00",
  guard_price: "",
  guard_triggered: "",
  exit_price: "",
  exit_time: "",
  status: "planned",
  notes: "",
};

const statusOptions = [
  { value: "planned", label: "计划中" },
  { value: "entered", label: "已买入" },
  { value: "holding", label: "持有中" },
  { value: "guard_exited", label: "10:00退出" },
  { value: "closed", label: "已完成" },
  { value: "skipped", label: "跳过" },
];

export default function MorningAuctionPage() {
  const [tradeDate, setTradeDate] = useState("");
  const [run, setRun] = useState<MorningAuctionRun | null>(null);
  const [trials, setTrials] = useState<MorningAuctionTrialEntry[]>([]);
  const [draft, setDraft] = useState<TrialDraft>(emptyDraft);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const topCandidates = run?.selected_pool ?? [];
  const attackCandidates = run?.attack_pool.slice(0, 12) ?? [];
  const allVisibleCandidates = useMemo(
    () => [...topCandidates, ...attackCandidates].slice(0, 15),
    [topCandidates, attackCandidates],
  );

  useEffect(() => {
    const latest = getLatestTradeDate();
    setTradeDate(latest);
    void refreshTrials(latest);
  }, []);

  async function refreshTrials(date: string) {
    try {
      const response = await listMorningAuctionTrials(date);
      setTrials(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取早盘试运行日志失败");
    }
  }

  async function handleRunModel() {
    setRunning(true);
    setError(null);
    try {
      const response = await predictMorningAuction(tradeDate);
      setRun(response);
      await refreshTrials(tradeDate);
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行早盘竞价模型失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleSaveTop3Plan() {
    if (!run || topCandidates.length === 0) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      for (const item of topCandidates) {
        await saveMorningAuctionTrial({
          trade_date: run.trade_date,
          symbol: item.symbol,
          name: item.name,
          rank: item.rank,
          prob_3pct: item.prob_3pct,
          mode: "live_small",
          status: "planned",
          guard_time: "10:00",
          notes: item.guard_rule ?? "Top3试运行计划",
        });
      }
      await refreshTrials(run.trade_date);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存 Top3 试运行计划失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveDraft() {
    if (!draft.symbol || !draft.trade_date) {
      setError("请选择候选或日志后再保存。");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveMorningAuctionTrial(draftToEntry(draft));
      await refreshTrials(draft.trade_date);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存试运行记录失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AdminShell>
      <div className="space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Morning Auction Research</p>
              <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">早盘竞价模型</h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
                这里只展示研究信号和实盘试运行日志。模型不连接券商，不自动下单；Top3 使用 10:00
                收益小于 0 则退出，否则按 T+1 收盘验证的规则跟踪。
              </p>
            </div>
            <div className="grid gap-2 sm:grid-cols-3 xl:min-w-[420px]">
              <SummaryMetric label="Top3" value={`${topCandidates.length}`} />
              <SummaryMetric label="试运行" value={`${trials.length}`} />
              <SummaryMetric label="守卫" value="10:00" />
            </div>
          </div>
        </header>

        {error && <p className="rounded-xl bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</p>}

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-xl font-black text-slate-950">生成今日候选</h2>
              <p className="mt-1 text-sm text-slate-500">线上预测使用目标日前最近一个已有日 K，避免使用当天收盘后的未来数据。</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <label className="text-sm font-bold text-slate-700">
                交易日
                <input
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm sm:w-40"
                  onChange={(event) => setTradeDate(event.target.value)}
                  type="date"
                  value={tradeDate}
                />
              </label>
              <button
                className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white disabled:bg-slate-300"
                disabled={running || !tradeDate}
                onClick={() => void handleRunModel()}
                type="button"
              >
                {running ? "运行中" : "运行模型"}
              </button>
              <button
                className="rounded-xl bg-emerald-50 px-4 py-2.5 text-sm font-bold text-emerald-700 disabled:opacity-50"
                disabled={saving || topCandidates.length === 0}
                onClick={() => void handleSaveTop3Plan()}
                type="button"
              >
                保存Top3计划
              </button>
            </div>
          </div>

          {run && (
            <div className="mt-4 flex flex-wrap gap-2">
              <StatusChip label={`模型 ${run.model_version}`} />
              <StatusChip label={`特征 ${run.feature_version}`} />
              {Object.entries(run.source_status).map(([key, value]) => (
                <StatusChip key={key} label={`${key}: ${value}`} />
              ))}
            </div>
          )}
        </section>

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-black text-slate-950">候选池</h2>
                <p className="mt-1 text-sm text-slate-500">Top3 是试运行核心，其余高分项只做攻击池观察。</p>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">
                {allVisibleCandidates.length} 只
              </span>
            </div>

            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-100">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-bold text-slate-500">
                  <tr>
                    <th className="px-4 py-3">排名</th>
                    <th className="px-4 py-3">股票</th>
                    <th className="px-4 py-3">概率</th>
                    <th className="px-4 py-3">分组</th>
                    <th className="px-4 py-3">规则</th>
                    <th className="px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {allVisibleCandidates.map((item) => (
                    <tr key={item.symbol} className="bg-white">
                      <td className="px-4 py-3 font-black text-slate-950">{item.rank ?? "-"}</td>
                      <td className="px-4 py-3">
                        <span className="block font-bold text-slate-950">{item.name || item.symbol}</span>
                        <span className="mt-1 block text-xs text-slate-500">{item.symbol}</span>
                      </td>
                      <td className="px-4 py-3 font-bold text-slate-800">{formatPct(item.prob_3pct)}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${bucketClass(item.bucket)}`}>
                          {bucketLabel(item.bucket)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        <span className="block">{item.guard_rule ?? "观察，不执行守卫"}</span>
                        <span className="mt-1 block">{item.data_quality.join("、") || "数据正常"}</span>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-700"
                          onClick={() => setDraft(draftFromCandidate(item, run?.trade_date ?? tradeDate))}
                          type="button"
                        >
                          记录
                        </button>
                      </td>
                    </tr>
                  ))}
                  {allVisibleCandidates.length === 0 && (
                    <tr>
                      <td className="px-4 py-6 text-sm text-slate-500" colSpan={6}>
                        尚未运行模型。选择交易日后点击“运行模型”。
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-xl font-black text-slate-950">实盘试运行记录</h2>
            <p className="mt-1 text-sm text-slate-500">手工记录成交和退出，不连接交易系统。</p>

            <div className="mt-4 space-y-3">
              {trials.map((entry) => (
                <button
                  key={entry.id ?? `${entry.trade_date}-${entry.symbol}`}
                  className="w-full rounded-xl border border-slate-100 bg-slate-50 p-3 text-left text-sm hover:bg-slate-100"
                  onClick={() => setDraft(draftFromEntry(entry))}
                  type="button"
                >
                  <span className="flex items-center justify-between gap-3">
                    <span>
                      <span className="block font-black text-slate-950">{entry.name || entry.symbol}</span>
                      <span className="mt-1 block text-xs text-slate-500">{entry.symbol}</span>
                    </span>
                    <span className="rounded-full bg-white px-2.5 py-1 text-xs font-bold text-slate-600">
                      {statusLabel(entry.status ?? "planned")}
                    </span>
                  </span>
                  <span className="mt-2 block text-xs text-slate-500">
                    买入 {entry.entry_price ?? "-"} · 守卫 {entry.guard_price ?? "-"} · 退出 {entry.exit_price ?? "-"}
                  </span>
                </button>
              ))}
              {trials.length === 0 && <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">暂无试运行记录。</p>}
            </div>

            <div className="mt-5 border-t border-slate-100 pt-5">
              <h3 className="text-sm font-black text-slate-950">编辑记录</h3>
              <div className="mt-3 grid gap-3">
                <Field label="股票" value={draft.symbol} onChange={(value) => setDraft({ ...draft, symbol: value })} />
                <Field label="名称" value={draft.name} onChange={(value) => setDraft({ ...draft, name: value })} />
                <div className="grid grid-cols-2 gap-2">
                  <Field label="计划资金" value={draft.planned_capital} onChange={(value) => setDraft({ ...draft, planned_capital: value })} />
                  <Field label="买入价" value={draft.entry_price} onChange={(value) => setDraft({ ...draft, entry_price: value })} />
                  <Field label="股数" value={draft.shares} onChange={(value) => setDraft({ ...draft, shares: value })} />
                  <Field label="10:00价" value={draft.guard_price} onChange={(value) => setDraft({ ...draft, guard_price: value })} />
                  <Field label="退出价" value={draft.exit_price} onChange={(value) => setDraft({ ...draft, exit_price: value })} />
                  <label className="text-xs font-bold text-slate-600">
                    状态
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                      onChange={(event) => setDraft({ ...draft, status: event.target.value })}
                      value={draft.status}
                    >
                      {statusOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <label className="text-xs font-bold text-slate-600">
                  备注
                  <textarea
                    className="mt-1 min-h-20 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                    onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
                    value={draft.notes}
                  />
                </label>
                <button
                  className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white disabled:bg-slate-300"
                  disabled={saving || !draft.symbol}
                  onClick={() => void handleSaveDraft()}
                  type="button"
                >
                  保存记录
                </button>
              </div>
            </div>
          </aside>
        </section>
      </div>
    </AdminShell>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className="text-xs font-bold text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-black text-slate-950">{value}</div>
    </div>
  );
}

function StatusChip({ label }: { label: string }) {
  return <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">{label}</span>;
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-xs font-bold text-slate-600">
      {label}
      <input
        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </label>
  );
}

function draftFromCandidate(item: MorningAuctionPredictionItem, tradeDate: string): TrialDraft {
  return {
    ...emptyDraft,
    trade_date: tradeDate,
    symbol: item.symbol,
    name: item.name,
    rank: item.rank?.toString() ?? "",
    prob_3pct: item.prob_3pct.toString(),
    notes: item.guard_rule ?? "候选观察",
  };
}

function draftFromEntry(entry: MorningAuctionTrialEntry): TrialDraft {
  return {
    ...emptyDraft,
    id: entry.id,
    trade_date: entry.trade_date,
    symbol: entry.symbol,
    name: entry.name ?? "",
    rank: entry.rank?.toString() ?? "",
    prob_3pct: entry.prob_3pct?.toString() ?? "",
    mode: entry.mode ?? "live_small",
    planned_capital: entry.planned_capital?.toString() ?? "",
    entry_price: entry.entry_price?.toString() ?? "",
    shares: entry.shares?.toString() ?? "",
    entry_time: entry.entry_time ?? "",
    guard_time: entry.guard_time ?? "10:00",
    guard_price: entry.guard_price?.toString() ?? "",
    guard_triggered: entry.guard_triggered === null || entry.guard_triggered === undefined ? "" : String(entry.guard_triggered),
    exit_price: entry.exit_price?.toString() ?? "",
    exit_time: entry.exit_time ?? "",
    status: entry.status ?? "planned",
    notes: entry.notes ?? "",
  };
}

function draftToEntry(draft: TrialDraft): MorningAuctionTrialEntry {
  return {
    id: draft.id,
    trade_date: draft.trade_date,
    symbol: draft.symbol,
    name: draft.name,
    rank: optionalInt(draft.rank),
    prob_3pct: optionalNumber(draft.prob_3pct),
    mode: draft.mode,
    planned_capital: optionalNumber(draft.planned_capital),
    entry_price: optionalNumber(draft.entry_price),
    shares: optionalInt(draft.shares),
    entry_time: draft.entry_time || null,
    guard_time: draft.guard_time || "10:00",
    guard_price: optionalNumber(draft.guard_price),
    guard_triggered: draft.guard_triggered === "" ? null : draft.guard_triggered === "true",
    exit_price: optionalNumber(draft.exit_price),
    exit_time: draft.exit_time || null,
    status: draft.status,
    notes: draft.notes,
  };
}

function optionalNumber(value: string): number | null {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : null;
}

function optionalInt(value: string): number | null {
  const parsed = optionalNumber(value);
  return parsed === null ? null : Math.trunc(parsed);
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function bucketLabel(bucket: string): string {
  if (bucket === "selected") return "Top3";
  if (bucket === "attack") return "攻击池";
  if (bucket === "watch") return "观察";
  return "规避";
}

function bucketClass(bucket: string): string {
  if (bucket === "selected") return "bg-red-50 text-red-700";
  if (bucket === "attack") return "bg-amber-50 text-amber-700";
  if (bucket === "watch") return "bg-slate-100 text-slate-600";
  return "bg-emerald-50 text-emerald-700";
}

function statusLabel(status: string): string {
  return statusOptions.find((option) => option.value === status)?.label ?? status;
}
