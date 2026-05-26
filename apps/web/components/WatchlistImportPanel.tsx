"use client";

import { useState } from "react";
import { confirmWatchlistOcr, importWatchlistFile, importWatchlistText, previewWatchlistOcr } from "../lib/api";
import type { WatchlistImportResult, WatchlistOcrPreviewResult } from "../lib/types";

export function WatchlistImportPanel({
  onImported,
}: {
  onImported: (result: WatchlistImportResult) => void;
}) {
  const [content, setContent] = useState("600000\n000001\n300750");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<WatchlistImportResult | null>(null);
  const [ocrPreview, setOcrPreview] = useState<WatchlistOcrPreviewResult | null>(null);
  const [confirmingOcr, setConfirmingOcr] = useState(false);

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

  async function handleOcrFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setRunning(true);
    setError(null);
    try {
      const result = await previewWatchlistOcr(file);
      setOcrPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "OCR 识别失败");
    } finally {
      setRunning(false);
      event.target.value = "";
    }
  }

  async function handleConfirmOcr() {
    if (!ocrPreview) return;
    setConfirmingOcr(true);
    setError(null);
    try {
      const result = await confirmWatchlistOcr(ocrPreview.preview_id);
      setLatest(result);
      setOcrPreview(null);
      onImported(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "OCR 导入失败");
    } finally {
      setConfirmingOcr(false);
    }
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-black text-slate-950">自选股导入</h2>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-500">
          同花顺 / OCR / CSV / 文本
        </span>
      </div>
      <textarea
        className="mt-3 min-h-28 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm"
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
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
        <label className="cursor-pointer rounded-2xl border border-slate-200 px-4 py-2.5 text-center text-sm font-bold text-slate-700 hover:border-slate-300">
          上传截图识别
          <input
            className="hidden"
            type="file"
            accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            onChange={handleOcrFileChange}
          />
        </label>
      </div>
      {error && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {ocrPreview && (
        <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs leading-6 text-amber-900">
          <div className="flex items-center justify-between gap-2">
            <div className="font-bold">OCR 识别预览 · {ocrPreview.item_count} 只</div>
            <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
              {ocrPreview.provider_status.provider}
              {ocrPreview.provider_status.fallback_used ? " fallback" : ""}
            </span>
          </div>
          <div className="mt-1 line-clamp-3 text-amber-800">
            {ocrPreview.items.map((item) => item.symbol).join("、") || "未识别到股票代码"}
          </div>
          {ocrPreview.warnings.length > 0 && <div className="mt-1 text-amber-700">{ocrPreview.warnings.join("；")}</div>}
          <details className="mt-2">
            <summary className="cursor-pointer font-semibold">查看 OCR 文本</summary>
            <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-xl bg-white/70 p-2 text-[11px] text-slate-700">
              {ocrPreview.ocr_text}
            </pre>
          </details>
          <button
            className="mt-3 w-full rounded-2xl bg-amber-600 px-4 py-2.5 text-sm font-bold text-white disabled:bg-amber-300"
            disabled={confirmingOcr}
            onClick={handleConfirmOcr}
            type="button"
          >
            {confirmingOcr ? "确认中..." : "确认导入 OCR 结果"}
          </button>
        </div>
      )}
      {latest && (
        <div className="mt-3 rounded-2xl bg-slate-50 p-3 text-xs leading-6 text-slate-600">
          <div className="font-bold text-slate-800">已导入 {latest.item_count} 只</div>
          <div className="mt-1 line-clamp-3">{latest.items.map((item) => item.symbol).join("、")}</div>
        </div>
      )}
    </section>
  );
}
