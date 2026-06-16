"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "../../components/AdminShell";
import { getTickFlowHealth, getWatchlistAlertSchedule } from "../../lib/api";
import type { TickFlowHealthStatus, WatchlistAlertScheduleStatus } from "../../lib/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<TickFlowHealthStatus | null>(null);
  const [schedule, setSchedule] = useState<WatchlistAlertScheduleStatus | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refreshSchedule();
  }, []);

  async function refreshSchedule() {
    try {
      const response = await getWatchlistAlertSchedule();
      setSchedule(response);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取提醒计划失败");
    }
  }

  async function runHealthCheck() {
    setLoadingHealth(true);
    setError(null);
    try {
      const response = await getTickFlowHealth();
      setHealth(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "TickFlow 健康检查失败");
    } finally {
      setLoadingHealth(false);
    }
  }

  return (
    <AdminShell>
      <div className="space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Settings</p>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">设置</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            这里集中看 TickFlow、提醒时间和通知渠道状态。健康检查需要手动触发，避免页面加载时消耗付费接口额度。
          </p>
        </header>

        {error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
          <div className="space-y-6">
            <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-xl font-black text-slate-950">TickFlow 健康检查</h2>
                  <p className="mt-1 text-sm text-slate-500">显示 Key、实时行情、日 K、分钟线、延迟、最近错误和 fallback 状态。</p>
                </div>
                <button
                  className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white disabled:bg-slate-300"
                  disabled={loadingHealth}
                  onClick={() => void runHealthCheck()}
                  type="button"
                >
                  {loadingHealth ? "检查中" : "手动检查"}
                </button>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <HealthMetric label="Key" value={health ? (health.configured ? "已配置" : "未配置") : "未检查"} />
                <HealthMetric label="实时行情" value={health?.realtime_quotes ?? "未检查"} />
                <HealthMetric label="日 K" value={health?.daily_kline ?? "未检查"} />
                <HealthMetric label="分钟线" value={health?.minute_kline ?? "未检查"} />
                <HealthMetric label="请求延迟" value={health?.latency_ms === null || health?.latency_ms === undefined ? "--" : `${health.latency_ms}ms`} />
                <HealthMetric label="Fallback" value={health?.fallback_source ?? "无"} />
              </div>
              <dl className="mt-4 grid gap-2 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                <InfoRow label="Base URL" value={health?.base_url ?? "--"} />
                <InfoRow label="状态" value={health?.status ?? "未检查"} />
                <InfoRow label="最近错误" value={health?.last_error ?? "无"} />
              </dl>
            </article>

            <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-black text-slate-950">提醒计划</h2>
              <p className="mt-1 text-sm text-slate-500">当前版本是定时扫描，不做实时监控；实时监控和任务流放到下一个版本。</p>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <ScheduleMetric label="早盘" value={schedule?.morning_time ?? "10:00"} />
                <ScheduleMetric label="午后" value={schedule?.afternoon_time ?? "14:30"} />
                <ScheduleMetric label="晚间复盘" value={schedule?.review_time ?? "19:30"} />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <SettingInput label="每日提醒上限" value="5" />
                <SettingInput label="过期复看周期" value="4 天" />
              </div>
              <dl className="mt-4 grid gap-2 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                <InfoRow label="启用状态" value={schedule?.enabled ? "已启用" : "未启用"} />
                <InfoRow label="时区" value={schedule?.timezone ?? "Asia/Shanghai"} />
                <InfoRow label="最近运行" value={schedule?.last_run_at ?? "暂无"} />
              </dl>
            </article>
          </div>

          <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-xl font-black text-slate-950">通知渠道</h2>
            <p className="mt-1 text-sm text-slate-500">企业微信、飞书、Telegram、邮件用于推送提醒摘要。</p>
            <div className="mt-4 space-y-3">
              <ChannelStatus name="企业微信" configured={false} />
              <ChannelStatus name="飞书" configured={false} />
              <ChannelStatus name="Telegram" configured={false} />
              <ChannelStatus name="邮件" configured={false} />
            </div>
          </aside>
        </section>
      </div>
    </AdminShell>
  );
}

function HealthMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 break-words text-lg font-black text-slate-950">{value}</div>
    </div>
  );
}

function ScheduleMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-black tabular-nums text-slate-950">{value}</div>
    </div>
  );
}

function SettingInput({ label, value }: { label: string; value: string }) {
  return (
    <label className="block text-sm font-bold text-slate-700">
      {label}
      <input className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 text-sm" readOnly value={value} />
    </label>
  );
}

function ChannelStatus({ name, configured }: { name: string; configured: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 p-3">
      <span className="font-bold text-slate-900">{name}</span>
      <span
        className={`rounded-full px-2.5 py-1 text-xs font-bold ${
          configured ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100" : "bg-slate-100 text-slate-500 ring-1 ring-slate-200"
        }`}
      >
        {configured ? "已配置" : "未配置"}
      </span>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="font-semibold text-slate-500">{label}</dt>
      <dd className="break-all text-right font-bold text-slate-800">{value}</dd>
    </div>
  );
}
