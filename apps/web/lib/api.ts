import type {
  ConfigStatusResponse,
  CreateReportResponse,
  DataSourceOptionsResponse,
  DataSourceOptionsUpdate,
  DeleteReportResponse,
  ReportScheduleStatus,
  ReportScheduleUpdate,
  ReportKind,
  ReportListResponse,
  TickFlowHealthStatus,
  WatchlistAlertEvent,
  WatchlistAlertListResponse,
  WatchlistAlertScheduleStatus,
  WatchlistImportResult,
  WatchlistOcrPreviewResult,
  WatchlistPoolGroup,
  WatchlistPoolState,
  WatchlistPoolStock,
  WatchlistStockPayload,
} from "./types";

function defaultApiBaseUrl(): string {
  if (typeof window !== "undefined" && window.location.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? defaultApiBaseUrl();

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

export async function deleteReport(reportId: number): Promise<DeleteReportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/reports/${reportId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`删除报告失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<DeleteReportResponse>;
}

export async function getConfigStatus(): Promise<ConfigStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/config/status`);
  if (!response.ok) {
    throw new Error(`读取数据源状态失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<ConfigStatusResponse>;
}

export async function getReportScheduleStatus(): Promise<ReportScheduleStatus> {
  const response = await fetch(`${API_BASE_URL}/api/report-schedule/status`);
  if (!response.ok) {
    throw new Error(`读取定时生成状态失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<ReportScheduleStatus>;
}

export async function updateReportScheduleStatus(
  payload: ReportScheduleUpdate,
): Promise<ReportScheduleStatus> {
  const response = await fetch(`${API_BASE_URL}/api/report-schedule/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`保存定时生成状态失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<ReportScheduleStatus>;
}

export async function listWatchlistAlerts(): Promise<WatchlistAlertListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alerts`);
  if (!response.ok) {
    throw new Error(`读取提醒列表失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistAlertListResponse>;
}

export async function runWatchlistAlerts(
  mode: string,
  tradeDate: string,
): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alerts/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, trade_date: tradeDate }),
  });
  if (!response.ok) {
    throw new Error(`运行提醒失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<Record<string, unknown>>;
}

export async function acknowledgeWatchlistAlert(alertId: number): Promise<WatchlistAlertEvent> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alerts/${alertId}/ack`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`标记提醒失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistAlertEvent>;
}

export async function muteWatchlistAlert(alertId: number, days: number): Promise<WatchlistAlertEvent> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alerts/${alertId}/mute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ days }),
  });
  if (!response.ok) {
    throw new Error(`暂不提醒失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistAlertEvent>;
}

export async function getWatchlistAlertSchedule(): Promise<WatchlistAlertScheduleStatus> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-alert-schedule/status`);
  if (!response.ok) {
    throw new Error(`读取提醒计划失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistAlertScheduleStatus>;
}

export async function getTickFlowHealth(): Promise<TickFlowHealthStatus> {
  const response = await fetch(`${API_BASE_URL}/api/tickflow/health`);
  if (!response.ok) {
    throw new Error(`读取TickFlow健康状态失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<TickFlowHealthStatus>;
}

export async function getWatchlistPool(): Promise<WatchlistPoolState> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-pool`);
  if (!response.ok) {
    throw new Error(`读取自选股池失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistPoolState>;
}

export async function createWatchlistGroup(name: string): Promise<WatchlistPoolGroup> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-pool/groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error(`新增分组失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistPoolGroup>;
}

export async function renameWatchlistGroup(groupId: number, name: string): Promise<WatchlistPoolGroup> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-pool/groups/${groupId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error(`重命名分组失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistPoolGroup>;
}

export async function deleteWatchlistGroup(groupId: number): Promise<{ deleted: boolean; id: number }> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-pool/groups/${groupId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`删除分组失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<{ deleted: boolean; id: number }>;
}

export async function createWatchlistStock(payload: WatchlistStockPayload): Promise<WatchlistPoolStock> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-pool/stocks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`加入自选股失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistPoolStock>;
}

export async function updateWatchlistStock(
  stockId: number,
  payload: WatchlistStockPayload,
): Promise<WatchlistPoolStock> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist-pool/stocks/${stockId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`保存自选股失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistPoolStock>;
}

export async function getDataSourceOptions(): Promise<DataSourceOptionsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/data-sources/options`);
  if (!response.ok) {
    throw new Error(`读取数据源选项失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<DataSourceOptionsResponse>;
}

export async function updateDataSourceOptions(
  payload: DataSourceOptionsUpdate,
): Promise<DataSourceOptionsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/data-sources/options`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`保存数据源选项失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<DataSourceOptionsResponse>;
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
