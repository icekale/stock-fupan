import type {
  CreateReportResponse,
  ReportKind,
  ReportListResponse,
  WatchlistImportResult,
  WatchlistOcrPreviewResult,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function createCloseReport(tradeDate: string): Promise<CreateReportResponse> {
  return createReport(tradeDate, "close");
}

export async function createReport(tradeDate: string, kind: ReportKind): Promise<CreateReportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/reports/${kind}`, {
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

export async function listReports(): Promise<ReportListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/reports`);
  if (!response.ok) {
    throw new Error(`读取报告列表失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<ReportListResponse>;
}

export function reportAssetUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
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

export async function previewWatchlistOcr(file: File): Promise<WatchlistOcrPreviewResult> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/watchlists/ocr-preview`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`OCR 识别失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistOcrPreviewResult>;
}

export async function confirmWatchlistOcr(previewId: string): Promise<WatchlistImportResult> {
  const response = await fetch(`${API_BASE_URL}/api/watchlists/ocr-confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preview_id: previewId }),
  });
  if (!response.ok) {
    throw new Error(`OCR 导入失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistImportResult>;
}
