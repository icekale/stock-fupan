"use client";

import { useState } from "react";
import { importWatchlistFile, importWatchlistText } from "../lib/api";
import type { WatchlistImportResult } from "../lib/types";

export function WatchlistImportPanel({
  onImported,
}: {
  onImported: (result: WatchlistImportResult) => void;
}) {
  const [content, setContent] = useState("600000\n000001\n300750");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<WatchlistImportResult | null>(null);

  async function handleTextImport() {
    setRunning(true);
    setError(null);
    try {
      const result = await importWatchlistText(content, "manual.txt");
      setLatest(result);
      onImported(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setRunning(true);
    setError(null);
    try {
      const result = await importWatchlistFile(file);
      setLatest(result);
      onImported(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setRunning(false);
      event.target.value = "";
    }
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-black text-slate-950">自选股导入</h2>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-500">
          同花顺 / CSV / 文本
        </span>
      </div>
      <textarea
        className="mt-3 min-h-28 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm"
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          className="rounded-2xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white disabled:bg-slate-300"
          disabled={running || content.trim().length === 0}
          onClick={handleTextImport}
          type="button"
        >
          {running ? "导入中..." : "导入文本"}
        </button>
        <label className="cursor-pointer rounded-2xl border border-slate-200 px-4 py-2.5 text-center text-sm font-bold text-slate-700 hover:border-slate-300">
          上传文件
          <input className="hidden" type="file" accept=".blk,.csv,.txt" onChange={handleFileChange} />
        </label>
      </div>
      {error && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {latest && (
        <div className="mt-3 rounded-2xl bg-slate-50 p-3 text-xs leading-6 text-slate-600">
          <div className="font-bold text-slate-800">已导入 {latest.item_count} 只</div>
          <div className="mt-1 line-clamp-3">{latest.items.map((item) => item.symbol).join("、")}</div>
        </div>
      )}
    </section>
  );
}
