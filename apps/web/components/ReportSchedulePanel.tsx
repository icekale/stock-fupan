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

  function updateDraft(update: Partial<ReportScheduleStatus>) {
    onChange({
      enabled,
      kind: status?.kind ?? "close",
      last_result: status?.last_result ?? null,
      last_run_at: status?.last_run_at ?? null,
      next_run_at: status?.next_run_at ?? null,
      time,
      timezone,
      ...update,
    });
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Schedule</p>
          <h2 className="mt-1 text-xl font-black text-slate-950">定时生成</h2>
        </div>
        <span className={`rounded-full px-3 py-1.5 text-xs font-bold ${enabled ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
          {enabled ? "已启用" : "已停用"}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_120px]">
        <label className="flex items-center justify-between rounded-2xl border border-slate-200 px-3 py-2.5 text-sm font-bold text-slate-700">
          <span>每天自动生成全日盘后日报</span>
          <input
            checked={enabled}
            className="h-5 w-5 accent-slate-950"
            onChange={(event) => updateDraft({ enabled: event.target.checked })}
            type="checkbox"
          />
        </label>
        <input
          aria-label="定时生成时间"
          className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-950 shadow-sm"
          onChange={(event) => updateDraft({ time: event.target.value })}
          type="time"
          value={time}
        />
      </div>

      <div className="mt-3 grid gap-2 rounded-2xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">
        <div>时区：{timezone}</div>
        <div>下次运行：{status?.next_run_at ?? "未启用"}</div>
        <div>
          最近结果：
          {status?.last_result ? `${status.last_result.trade_date} ${status.last_result.status}` : "暂无"}
        </div>
      </div>

      {error && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm leading-6 text-red-700">{error}</p>}
      <button
        className="mt-3 w-full rounded-2xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white disabled:bg-slate-300"
        disabled={saving || !status}
        onClick={onSave}
        type="button"
      >
        {saving ? "保存中..." : "保存定时设置"}
      </button>
    </section>
  );
}
