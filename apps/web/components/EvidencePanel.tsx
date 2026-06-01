"use client";

import { useState } from "react";
import {
  parseEvidencePreview,
  saveEvidenceItems,
  searchEvidenceCandidates,
} from "../lib/api";
import type { EvidenceParsePreview } from "../lib/types";

type EvidencePanelProps = {
  tradeDate: string;
};

const sampleEvidence = `[
  {
    "trade_date": "2026-06-01",
    "source": "证券时报",
    "title": "煤炭行业今日净流入资金26.55亿元",
    "url": "https://example.com/stcn/coal",
    "published_at": "2026-06-01T15:30:00+08:00",
    "category": "capital_flow",
    "claim": "煤炭行业今日净流入资金26.55亿元。",
    "numbers": {"industry": "煤炭", "net_inflow_yi": 26.55},
    "related_sectors": ["煤炭"],
    "confidence": "high",
    "status": "verified"
  }
]`;

export function EvidencePanel({ tradeDate }: EvidencePanelProps) {
  const [content, setContent] = useState(sampleEvidence);
  const [preview, setPreview] = useState<EvidenceParsePreview | null>(null);
  const [task, setTask] = useState("stcn_capital_flow");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function handlePreview() {
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      const response = await parseEvidencePreview(content);
      setPreview(response);
      setMessage(`解析完成：有效 ${response.valid_count} 条，异常 ${response.invalid_count} 条`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "解析证据失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleSave() {
    const validItems = preview?.items.flatMap((item) => (item.item && item.errors.length === 0 ? [item.item] : [])) ?? [];
    if (validItems.length === 0) {
      setError("没有可保存的有效证据");
      return;
    }
    const verifiedItems = validItems.filter((item) => item.status === "verified");
    if (verifiedItems.length === 0) {
      setError("候选证据需要手工确认为 verified 后才能保存为日报证据");
      return;
    }
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      const response = await saveEvidenceItems(verifiedItems);
      setMessage(`已保存 ${response.items.length} 条证据`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存证据失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleCandidateSearch() {
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      const response = await searchEvidenceCandidates(tradeDate, task, query);
      setPreview({
        items: response.items,
        valid_count: response.items.filter((item) => item.errors.length === 0).length,
        invalid_count: response.items.filter((item) => item.errors.length > 0).length,
      });
      setMessage(`Anspire 候选：${response.items.length} 条，状态 ${response.provider_status.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "搜索候选证据失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section id="evidence" className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Evidence</p>
          <h2 className="mt-1 text-xl font-black text-slate-950">日报证据</h2>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">{tradeDate}</span>
      </div>

      <textarea
        className="mt-4 min-h-48 w-full rounded-2xl border border-slate-200 bg-white p-3 text-sm text-slate-950 shadow-sm"
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          className="rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-300"
          disabled={running}
          onClick={handlePreview}
          type="button"
        >
          解析预览
        </button>
        <button
          className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-300"
          disabled={running || !preview}
          onClick={handleSave}
          type="button"
        >
          保存有效证据
        </button>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50 p-3">
        <div className="grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)_auto]">
          <select
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            value={task}
            onChange={(event) => setTask(event.target.value)}
          >
            <option value="stcn_capital_flow">证券时报行业资金</option>
            <option value="jrj_continuous_outflow">金融界连续净流出</option>
            <option value="catalysts">搜狐/36氪/快科技/新浪催化</option>
            <option value="custom">自定义关键词</option>
          </select>
          <input
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="自定义 Anspire 查询，可留空使用预设"
          />
          <button
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-300"
            disabled={running}
            onClick={handleCandidateSearch}
            type="button"
          >
            Anspire 候选
          </button>
        </div>
      </div>

      {message && <p className="mt-3 rounded-2xl bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p>}
      {error && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      {preview && (
        <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100">
          {preview.items.map((item, index) => (
            <article className="border-b border-slate-100 p-3 text-sm last:border-b-0" key={`${item.item?.title ?? "raw"}-${index}`}>
              <div className="font-bold text-slate-950">{item.item?.title ?? "无法解析"}</div>
              <div className="mt-1 text-xs text-slate-500">
                {item.item ? `${item.item.source} · ${item.item.category} · ${item.item.confidence} · ${item.item.status}` : String(item.raw)}
              </div>
              {item.item && <p className="mt-2 text-slate-700">{item.item.claim}</p>}
              {item.errors.length > 0 && <p className="mt-2 text-red-700">{item.errors.join("；")}</p>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
