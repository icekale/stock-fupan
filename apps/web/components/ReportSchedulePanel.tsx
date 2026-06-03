import type { ReportScheduleStatus } from "../lib/types";

type ReportSchedulePanelProps = {
  error: string | null;
  onChange: (status: ReportScheduleStatus) => void;
  onSave: () => void;
  saving: boolean;
  status: ReportScheduleStatus | null;
};

export function ReportSchedulePanel({
  error,
  onChange,
  onSave,
  saving,
  status,
}: ReportSchedulePanelProps) {
  const enabled = status?.enabled ?? false;
  const time = status?.time ?? "19:00";
  const timezone = status?.timezone ?? "Asia/Shanghai";
  const loading = !status && !error;
  const nextRunText = enabled
    ? formatScheduleDateTime(status?.next_run_at, timezone, "等待调度")
    : "未启用";
  const lastRunText = formatScheduleDateTime(status?.last_run_at, timezone, "暂无");
  const lastResultText = status?.last_result
    ? `${status.last_result.trade_date} ${formatLastResultStatus(status.last_result.status)}`
    : "暂无";

  function updateDraft(update: Partial<ReportScheduleStatus>) {
    onChange({
      enabled,
      kind: "close",
      last_result: status?.last_result ?? null,
      last_run_at: status?.last_run_at ?? null,
      next_run_at: status?.next_run_at ?? null,
      time,
      timezone,
      ...update,
    });
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Schedule</p>
          <h2 className="mt-1 text-xl font-black text-slate-950">定时生成</h2>
        </div>
        <span
          className={`inline-flex h-7 items-center rounded-full px-3 text-xs font-bold ring-1 ${
            loading
              ? "bg-slate-50 text-slate-500 ring-slate-200"
              : enabled
                ? "bg-emerald-50 text-emerald-700 ring-emerald-100"
                : "bg-slate-100 text-slate-600 ring-slate-200"
          }`}
        >
          {loading ? "读取中" : enabled ? "已启用" : "已停用"}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_124px]">
        <button
          aria-checked={enabled}
          className="flex min-h-[48px] items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-left text-sm font-bold text-slate-800 transition hover:border-slate-300 hover:bg-white active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60 disabled:active:translate-y-0"
          disabled={!status || saving}
          onClick={() => updateDraft({ enabled: !enabled })}
          role="switch"
          type="button"
        >
          <span>
            <span className="block">每天自动生成全日盘后日报</span>
            <span className="mt-0.5 block text-xs font-semibold text-slate-500">
              {enabled ? "到点自动生成 close 日报" : "关闭后只保留手动生成"}
            </span>
          </span>
          <span
            className={`relative h-6 w-11 shrink-0 rounded-full transition ${
              enabled ? "bg-slate-950" : "bg-slate-300"
            }`}
            aria-hidden="true"
          >
            <span
              className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${
                enabled ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </span>
        </button>
        <input
          aria-label="定时生成时间"
          className="min-h-[48px] rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-950 shadow-sm transition hover:border-slate-300 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
          disabled={!status || saving}
          onChange={(event) => updateDraft({ time: event.target.value })}
          type="time"
          value={time}
        />
      </div>

      <dl className="mt-3 grid gap-2 rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
        <ScheduleInfoItem label="执行时间" value={`${time} (${timezone})`} />
        <ScheduleInfoItem label="下次运行" value={loading ? "读取定时设置" : nextRunText} />
        <ScheduleInfoItem label="最近运行" value={lastRunText} />
        <ScheduleInfoItem label="最近结果" value={lastResultText} />
      </dl>

      {status?.last_result?.reason && (
        <p className="mt-3 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">
          最近原因：{status.last_result.reason}
        </p>
      )}
      {error && <p className="mt-3 rounded-xl bg-red-50 p-3 text-sm leading-6 text-red-700">{error}</p>}
      <button
        className="mt-3 w-full rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-slate-800 active:translate-y-px disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:active:translate-y-0"
        disabled={saving || !status}
        onClick={onSave}
        type="button"
      >
        {saving ? "保存定时设置中" : loading ? "读取定时设置" : "保存定时设置"}
      </button>
    </section>
  );
}

function ScheduleInfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="font-semibold text-slate-500">{label}</dt>
      <dd className="text-right font-bold text-slate-800">{value}</dd>
    </div>
  );
}

function formatScheduleDateTime(
  value: string | null | undefined,
  timezone: string,
  fallback: string,
): string {
  if (!value) {
    return fallback;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: timezone,
    }).format(date);
  } catch {
    return date.toLocaleString("zh-CN");
  }
}

function formatLastResultStatus(status: string): string {
  if (status === "success" || status === "generated_publishable") {
    return "成功";
  }
  if (status === "generated_degraded") {
    return "降级生成";
  }
  if (status === "generated_blocked") {
    return "生成草稿";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "skipped" || status.startsWith("skipped_existing_")) {
    return "跳过";
  }
  return status;
}
