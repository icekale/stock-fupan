import type { CreateReportResponse, WatchlistImportResult } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function createCloseReport(tradeDate: string): Promise<CreateReportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/reports/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trade_date: tradeDate }),
  });

  if (!response.ok) {
    let detail = response.statusText;
    const bodyText = await response.text();

    if (bodyText) {
      try {
        const payload = JSON.parse(bodyText) as { detail?: unknown; message?: unknown };
        const message = payload.detail ?? payload.message;
        if (typeof message === "string") {
          detail = message;
        } else {
          detail = bodyText;
        }
      } catch {
        detail = bodyText;
      }
    }

    throw new Error(`生成失败：${response.status} ${detail}`);
  }

  return response.json() as Promise<CreateReportResponse>;
}

export async function importWatchlistText(
  content: string,
  sourceName = "manual.txt",
): Promise<WatchlistImportResult> {
  const response = await fetch(`${API_BASE_URL}/api/watchlists/import-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, source_name: sourceName }),
  });
  if (!response.ok) {
    throw new Error(`导入失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistImportResult>;
}

export async function importWatchlistFile(file: File): Promise<WatchlistImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/watchlists/import-file`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`导入失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistImportResult>;
}
