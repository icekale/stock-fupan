"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/AdminShell";
import {
  createWatchlistGroup,
  createWatchlistStock,
  deleteWatchlistGroup,
  getWatchlistPool,
  listWatchlistAlerts,
  renameWatchlistGroup,
  updateWatchlistStock,
} from "../../lib/api";
import type { WatchlistAlertEvent, WatchlistPoolGroup, WatchlistPoolState, WatchlistPoolStock } from "../../lib/types";

type StockDraft = {
  symbol: string;
  name: string;
  status: "观察中" | "持有中";
  tags: string;
  themes: string;
  entry_reason: string;
  planned_buy_price: string;
  invalid_condition: string;
  last_review_conclusion: string;
  today_risk_hint: string;
};

const emptyDraft: StockDraft = {
  symbol: "",
  name: "",
  status: "观察中",
  tags: "",
  themes: "",
  entry_reason: "",
  planned_buy_price: "",
  invalid_condition: "",
  last_review_conclusion: "",
  today_risk_hint: "",
};

export default function WatchlistPage() {
  const [pool, setPool] = useState<WatchlistPoolState>({ groups: [], stocks: [] });
  const [alerts, setAlerts] = useState<WatchlistAlertEvent[]>([]);
  const [selectedStockId, setSelectedStockId] = useState<number | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<number | "all">("all");
  const [query, setQuery] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [renamingGroupId, setRenamingGroupId] = useState<number | null>(null);
  const [renameGroupName, setRenameGroupName] = useState("");
  const [createDraft, setCreateDraft] = useState<StockDraft>(emptyDraft);
  const [editDraft, setEditDraft] = useState<StockDraft>(emptyDraft);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedStock = pool.stocks.find((stock) => stock.id === selectedStockId) ?? pool.stocks[0] ?? null;
  const visibleStocks = useMemo(() => {
    const keyword = query.trim().toUpperCase();
    return pool.stocks.filter((stock) => {
      const groupMatched =
        selectedGroupId === "all" || stock.groups.some((group) => group.id === selectedGroupId);
      const keywordMatched =
        !keyword ||
        stock.symbol.toUpperCase().includes(keyword) ||
        (stock.name ?? "").toUpperCase().includes(keyword) ||
        stock.tags.join(",").toUpperCase().includes(keyword) ||
        stock.themes.join(",").toUpperCase().includes(keyword);
      return groupMatched && keywordMatched;
    });
  }, [pool.stocks, query, selectedGroupId]);

  const alertsBySymbol = useMemo(() => {
    const map = new Map<string, WatchlistAlertEvent>();
    for (const alert of alerts) {
      if (!map.has(alert.symbol)) {
        map.set(alert.symbol, alert);
      }
    }
    return map;
  }, [alerts]);

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (selectedStock) {
      setEditDraft(stockToDraft(selectedStock));
    } else {
      setEditDraft(emptyDraft);
    }
  }, [selectedStock?.id]);

  async function refresh() {
    try {
      const [poolResponse, alertResponse] = await Promise.all([getWatchlistPool(), listWatchlistAlerts()]);
      setPool(poolResponse);
      setAlerts(alertResponse.items);
      setSelectedStockId((current) =>
        current && poolResponse.stocks.some((stock) => stock.id === current) ? current : (poolResponse.stocks[0]?.id ?? null),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取自选股池失败");
    }
  }

  async function handleCreateGroup() {
    if (!newGroupName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createWatchlistGroup(newGroupName);
      setNewGroupName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "新增分组失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleRenameGroup(group: WatchlistPoolGroup) {
    if (!renameGroupName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await renameWatchlistGroup(group.id, renameGroupName);
      setRenamingGroupId(null);
      setRenameGroupName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重命名分组失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteGroup(group: WatchlistPoolGroup) {
    if (!window.confirm(`确认删除分组 ${group.name} 吗？股票会保留在自选股池中。`)) return;
    setSaving(true);
    setError(null);
    try {
      await deleteWatchlistGroup(group.id);
      if (selectedGroupId === group.id) {
        setSelectedGroupId("all");
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除分组失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddStock() {
    if (!createDraft.symbol.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createWatchlistStock(draftToPayload(createDraft, null));
      setSelectedStockId(created.id);
      setCreateDraft(emptyDraft);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "加入自选股失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveStock() {
    if (!selectedStock) return;
    setSaving(true);
    setError(null);
    try {
      await updateWatchlistStock(selectedStock.id, draftToPayload(editDraft, selectedStock));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存自选股失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleGroup(stock: WatchlistPoolStock, group: WatchlistPoolGroup) {
    const groupIds = stock.groups.some((item) => item.id === group.id)
      ? stock.groups.filter((item) => item.id !== group.id).map((item) => item.id)
      : [...stock.groups.map((item) => item.id), group.id];
    try {
      await updateWatchlistStock(stock.id, { group_ids: groupIds });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新多分组失败");
    }
  }

  return (
    <AdminShell>
      <div className="space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Watchlist Pool</p>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">自选股池</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            从长列表变成观察池：分组、标签、加入理由、计划买点、失效条件、所属题材、上次复盘结论和今天风险提示都沉淀在这里。
          </p>
        </header>

        {error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-4">
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-black text-slate-950">新增分组</h2>
              <div className="mt-3 flex gap-2">
                <input
                  className="min-h-11 min-w-0 flex-1 rounded-xl border border-slate-200 px-3 text-sm"
                  onChange={(event) => setNewGroupName(event.target.value)}
                  placeholder="如 MLCC、电力、存储芯片"
                  value={newGroupName}
                />
                <button
                  className="rounded-xl bg-slate-950 px-4 text-sm font-bold text-white disabled:bg-slate-300"
                  disabled={saving || !newGroupName.trim()}
                  onClick={() => void handleCreateGroup()}
                  type="button"
                >
                  新增
                </button>
              </div>
              <div className="mt-4 space-y-2">
                <button
                  className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm font-bold ${
                    selectedGroupId === "all" ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-700"
                  }`}
                  onClick={() => setSelectedGroupId("all")}
                  type="button"
                >
                  <span>全部</span>
                  <span>{pool.stocks.length}</span>
                </button>
                {pool.groups.map((group) => (
                  <div key={group.id} className="rounded-xl border border-slate-100 bg-slate-50 p-2">
                    {renamingGroupId === group.id ? (
                      <div className="flex gap-2">
                        <input
                          className="min-h-9 min-w-0 flex-1 rounded-lg border border-slate-200 px-2 text-sm"
                          onChange={(event) => setRenameGroupName(event.target.value)}
                          value={renameGroupName}
                        />
                        <button className="rounded-lg bg-slate-950 px-3 text-xs font-bold text-white" onClick={() => void handleRenameGroup(group)} type="button">
                          保存
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <button
                          className={`min-w-0 flex-1 rounded-lg px-3 py-2 text-left text-sm font-bold ${
                            selectedGroupId === group.id ? "bg-slate-950 text-white" : "bg-white text-slate-700"
                          }`}
                          onClick={() => setSelectedGroupId(group.id)}
                          type="button"
                        >
                          {group.name}
                        </button>
                        <button
                          className="rounded-lg bg-white px-2 py-2 text-xs font-bold text-slate-600"
                          onClick={() => {
                            setRenamingGroupId(group.id);
                            setRenameGroupName(group.name);
                          }}
                          type="button"
                        >
                          编辑
                        </button>
                        <button
                          className="rounded-lg bg-red-50 px-2 py-2 text-xs font-bold text-red-700 disabled:opacity-40"
                          disabled={group.is_default}
                          onClick={() => void handleDeleteGroup(group)}
                          type="button"
                        >
                          删除分组
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-black text-slate-950">加入自选</h2>
              <p className="mt-1 text-xs text-slate-500">输入代码后保存，后续可自由划入多分组。</p>
              <PlanEditor draft={createDraft} onChange={setCreateDraft} compact />
              <button
                className="mt-3 w-full rounded-xl bg-slate-950 px-4 py-3 text-sm font-bold text-white disabled:bg-slate-300"
                disabled={saving || !createDraft.symbol.trim()}
                onClick={() => void handleAddStock()}
                type="button"
              >
                加入自选股池
              </button>
            </section>
          </aside>

          <section className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-xl font-black text-slate-950">观察列表</h2>
                  <p className="mt-1 text-sm text-slate-500">多分组、状态和关键词筛选，快速定位股票。</p>
                </div>
                <input
                  className="min-h-11 rounded-xl border border-slate-200 px-3 text-sm"
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索代码、名称、标签、题材"
                  value={query}
                />
              </div>

              <div className="mt-4 overflow-hidden rounded-xl border border-slate-100">
                <div className="grid grid-cols-[120px_1fr_120px_130px] gap-3 bg-slate-50 px-4 py-3 text-xs font-bold text-slate-500">
                  <span>代码</span>
                  <span>分组 / 标签 / 多分组</span>
                  <span>状态</span>
                  <span>最近提醒</span>
                </div>
                {visibleStocks.map((stock) => {
                  const alert = alertsBySymbol.get(stock.symbol);
                  return (
                    <button
                      key={stock.id}
                      className={`grid w-full grid-cols-[120px_1fr_120px_130px] gap-3 border-t border-slate-100 px-4 py-3 text-left text-sm ${
                        selectedStock?.id === stock.id ? "bg-slate-50" : "bg-white hover:bg-slate-50"
                      }`}
                      onClick={() => setSelectedStockId(stock.id)}
                      type="button"
                    >
                      <span>
                        <span className="block font-black text-slate-950">{stock.name ?? stock.symbol}</span>
                        <span className="mt-1 block text-xs text-slate-500">{stock.symbol}</span>
                      </span>
                      <span className="space-y-2">
                        <span className="flex flex-wrap gap-1.5">
                          {pool.groups.map((group) => (
                            <label
                              key={`${stock.id}-${group.id}`}
                              className="inline-flex cursor-pointer items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <input
                                checked={stock.groups.some((item) => item.id === group.id)}
                                className="accent-slate-950"
                                onChange={() => void handleToggleGroup(stock, group)}
                                type="checkbox"
                              />
                              {group.name}
                            </label>
                          ))}
                        </span>
                        <span className="block text-xs text-slate-500">
                          {[...stock.tags, ...stock.themes].join("、") || "暂无标签"}
                        </span>
                      </span>
                      <span className={stock.status === "持有中" ? "font-bold text-red-600" : "font-bold text-slate-700"}>
                        {stock.status}
                      </span>
                      <span className="text-xs leading-5 text-slate-500">
                        {alert ? `${severityLabel(alert.severity)} · ${alert.trigger_reason}` : "暂无"}
                      </span>
                    </button>
                  );
                })}
                {visibleStocks.length === 0 && <p className="border-t border-slate-100 p-5 text-sm text-slate-500">暂无匹配股票。</p>}
              </div>
            </div>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-xl font-black text-slate-950">观察计划</h2>
                  <p className="mt-1 text-sm text-slate-500">用户手写字段不会被 AI 自动覆盖，复盘结果只写回结论和风险提示。</p>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">
                  {selectedStock ? `${selectedStock.symbol} · ${selectedStock.name ?? "未命名"}` : "未选择"}
                </span>
              </div>
              <div className="mt-4">
                <PlanEditor draft={editDraft} onChange={setEditDraft} />
              </div>
              <button
                className="mt-4 rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white disabled:bg-slate-300"
                disabled={!selectedStock || saving}
                onClick={() => void handleSaveStock()}
                type="button"
              >
                保存观察计划
              </button>
            </section>
          </section>
        </div>
      </div>
    </AdminShell>
  );
}

function PlanEditor({
  compact = false,
  draft,
  onChange,
}: {
  compact?: boolean;
  draft: StockDraft;
  onChange: (draft: StockDraft) => void;
}) {
  const fields: Array<{ key: keyof StockDraft; label: string; placeholder: string }> = [
    { key: "symbol", label: "代码", placeholder: "600563.SH" },
    { key: "name", label: "名称", placeholder: "可选" },
    { key: "tags", label: "标签", placeholder: "趋势, 观察" },
    { key: "themes", label: "所属题材", placeholder: "MLCC, 消费电子" },
    { key: "entry_reason", label: "加入理由", placeholder: "为什么进入观察池" },
    { key: "planned_buy_price", label: "计划买点", placeholder: "如回踩 MA10 / 突破平台" },
    { key: "invalid_condition", label: "失效条件", placeholder: "跌破什么就移出或复核" },
    { key: "last_review_conclusion", label: "上次复盘结论", placeholder: "上次观察结论" },
    { key: "today_risk_hint", label: "今天风险提示", placeholder: "今日需要警惕的信号" },
  ];
  const visibleFields = compact ? fields.slice(0, 4) : fields;

  return (
    <div className={`grid gap-3 ${compact ? "" : "md:grid-cols-2"}`}>
      {!compact && (
        <label className="block text-sm font-semibold text-slate-700">
          状态
          <select
            className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 text-sm"
            onChange={(event) => onChange({ ...draft, status: event.target.value as StockDraft["status"] })}
            value={draft.status}
          >
            <option>观察中</option>
            <option>持有中</option>
          </select>
        </label>
      )}
      {visibleFields.map((field) => (
        <label key={field.key} className="block text-sm font-semibold text-slate-700">
          {field.label}
          <input
            className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 text-sm"
            onChange={(event) => onChange({ ...draft, [field.key]: event.target.value })}
            placeholder={field.placeholder}
            value={draft[field.key]}
          />
        </label>
      ))}
    </div>
  );
}

function stockToDraft(stock: WatchlistPoolStock): StockDraft {
  return {
    symbol: stock.symbol,
    name: stock.name ?? "",
    status: stock.status,
    tags: stock.tags.join(", "),
    themes: stock.themes.join(", "),
    entry_reason: stock.entry_reason ?? "",
    planned_buy_price: stock.planned_buy_price ?? "",
    invalid_condition: stock.invalid_condition ?? "",
    last_review_conclusion: stock.last_review_conclusion ?? "",
    today_risk_hint: stock.today_risk_hint ?? "",
  };
}

function draftToPayload(draft: StockDraft, stock: WatchlistPoolStock | null) {
  const payload: Record<string, unknown> = {};
  if (draft.symbol.trim()) payload.symbol = draft.symbol.trim();
  if (draft.name.trim()) payload.name = draft.name.trim();
  payload.status = draft.status;
  if (stock) payload.group_ids = stock.groups.map((group) => group.id);
  const tags = splitList(draft.tags);
  const themes = splitList(draft.themes);
  if (tags.length > 0) payload.tags = tags;
  if (themes.length > 0) payload.themes = themes;
  if (draft.entry_reason) payload.entry_reason = draft.entry_reason;
  if (draft.planned_buy_price) payload.planned_buy_price = draft.planned_buy_price;
  if (draft.invalid_condition) payload.invalid_condition = draft.invalid_condition;
  if (draft.last_review_conclusion) payload.last_review_conclusion = draft.last_review_conclusion;
  if (draft.today_risk_hint) payload.today_risk_hint = draft.today_risk_hint;
  return payload;
}

function splitList(value: string): string[] {
  return value
    .split(/[,\s，、]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function severityLabel(severity: WatchlistAlertEvent["severity"]) {
  return {
    high: "高危",
    medium: "关注",
    low: "低",
  }[severity];
}
