import type { ProviderStatusSummary, SectorProviderStatus } from "../lib/types";

export function ProviderStatusPanel({ status }: { status: ProviderStatusSummary }) {
  const newsFallbacks = status.news.filter((item) => item.fallback_used);
  const tickflowFallback = status.tickflow?.fallback_used ?? false;
  const allReal = !status.market.fallback_used && newsFallbacks.length === 0 && !tickflowFallback;

  return (
    <section
      className={`rounded-2xl border px-4 py-3 text-sm ${
        allReal
          ? "border-emerald-200 bg-emerald-50 text-emerald-900"
          : "border-amber-200 bg-amber-50 text-amber-950"
      }`}
      aria-label="数据源诊断"
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="font-bold">{allReal ? "真实数据源已启用" : "数据源回退提示"}</div>
        <div className="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
          Market {status.market.provider} · News {summarizeNewsProviders(status.news)}
          {status.tickflow ? ` · TickFlow ${status.tickflow.provider}` : ""}
        </div>
      </div>

      {allReal ? (
        <p className="mt-2 leading-6">
          行情使用 {status.market.provider}，新闻使用 {summarizeNewsProviders(status.news)}；未触发 fake 回退。
        </p>
      ) : (
        <ul className="mt-2 list-disc space-y-1 pl-5 leading-6">
          {status.market.fallback_used && (
            <li>
              行情源 {status.market.provider} 已回退 fake：{status.market.reason ?? "未知原因"}
            </li>
          )}
          {newsFallbacks.slice(0, 5).map((item) => (
            <li key={`${item.sector}-${item.provider}`}>
              新闻源 {item.provider}（{item.sector}）已回退 fake：{item.reason ?? "未知原因"}
            </li>
          ))}
          {newsFallbacks.length > 5 && <li>还有 {newsFallbacks.length - 5} 条新闻源回退。</li>}
          {status.tickflow?.fallback_used && (
            <li>TickFlow 已回退 fake：{status.tickflow.reason ?? "未知原因"}</li>
          )}
        </ul>
      )}
    </section>
  );
}

function summarizeNewsProviders(items: SectorProviderStatus[]) {
  const providers = Array.from(new Set(items.map((item) => item.provider)));
  return providers.length > 0 ? providers.join("、") : "无新闻源";
}
