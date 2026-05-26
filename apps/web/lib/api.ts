import type { CreateReportResponse } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function createCloseReport(tradeDate: string): Promise<CreateReportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/reports/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trade_date: tradeDate }),
  });

  if (!response.ok) {
    let detail = response.statusText;

    try {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown };
      const message = payload.detail ?? payload.message;
      if (typeof message === "string") {
        detail = message;
      }
    } catch {
      const text = await response.text().catch(() => "");
      if (text) {
        detail = text;
      }
    }

    throw new Error(`生成失败：${response.status} ${detail}`);
  }

  return response.json() as Promise<CreateReportResponse>;
}
