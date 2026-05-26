import type { CreateReportResponse } from "../lib/types";
import { ProviderStatusPanel } from "./ProviderStatusPanel";

export function ReportPreview({ result }: { result: CreateReportResponse }) {
  const { report, validation, assets } = result;

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
      <header className="flex flex-col gap-4 border-b border-slate-100 pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">A-Share Market Review</p>
          <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">{report.title}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {report.market_state_tags.map((tag) => (
              <span key={tag} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                {tag}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white">{assets.version}</span>
          <span
            className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
              validation.is_valid ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
            }`}
          >
            {validation.is_valid ? "校验通过" : "需修正"}
          </span>
        </div>
      </header>

      <div className="mt-5">
        <ProviderStatusPanel status={result.provider_status} />
      </div>

      <section className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="市场概览指标">
        <Metric label="上涨 / 下跌" value={`${report.breadth.up_count} / ${report.breadth.down_count}`} tone="slate" />
        <Metric label="涨停" value={`${report.breadth.limit_up_count} 只`} tone="red" />
        <Metric label="跌停" value={`${report.breadth.limit_down_count} 只`} tone="green" />
        <Metric label="成交额" value={`${report.turnover_cny.toFixed(2)} 亿`} tone="slate" />
      </section>

      {report.watchlist_observation && (
        <section className="mt-5 rounded-2xl border border-amber-100 bg-amber-50/60 p-4">
          <h3 className="text-sm font-black text-slate-950">自选股观察</h3>
          <p className="mt-1 text-xs text-slate-500">
            导入 {report.watchlist_observation.total_count} 只，行情匹配 {report.watchlist_observation.quote_count} 只
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {report.watchlist_observation.strongest.slice(0, 3).map((item) => (
              <div key={`strong-${item.symbol}`} className="rounded-xl bg-white px-3 py-2 text-sm">
                <div className="font-bold text-slate-900">{item.name ?? item.symbol}</div>
                <div className="mt-1 text-red-600">
                  {item.pct_change?.toFixed(2) ?? "--"}% · {item.symbol}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {report.indices.length > 0 && (
        <section className="mt-5 rounded-2xl bg-slate-50 p-4">
          <h3 className="text-sm font-bold text-slate-900">指数表现</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {report.indices.map((index) => (
              <div key={index.code} className="rounded-xl bg-white px-3 py-2">
                <div className="text-sm font-semibold text-slate-800">{index.name}</div>
                <div className="mt-1 flex items-baseline justify-between gap-2">
                  <span className="text-sm tabular-nums text-slate-500">{index.close.toFixed(2)}</span>
                  <span className={index.pct_change >= 0 ? "text-sm font-bold text-red-600" : "text-sm font-bold text-emerald-700"}>
                    {index.pct_change.toFixed(2)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="mt-6">
        <SectionTitle>先给结论</SectionTitle>
        <p className="mt-3 leading-7 text-slate-700">{report.narrative.conclusion}</p>
      </section>

      <section className="mt-6">
        <SectionTitle>强势板块</SectionTitle>
        <div className="mt-3 grid gap-3">
          {report.sectors.map((sector) => (
            <div key={sector.name} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="font-bold text-slate-950">
                  {sector.rank}. {sector.name}
                </div>
                <div className="flex items-center gap-3 text-sm">
                  <span className="font-semibold text-slate-500">评分 {sector.score.toFixed(1)}</span>
                  <span className={sector.pct_change >= 0 ? "font-bold text-red-600" : "font-bold text-emerald-700"}>
                    {sector.pct_change.toFixed(2)}%
                  </span>
                </div>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-600">{sector.news_summaries[0] ?? sector.reason}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-6 grid gap-3 lg:grid-cols-2">
        <NarrativeBlock title="明日关注" items={report.narrative.watchlist} fallback={report.narrative.tomorrow} />
        <NarrativeBlock title="风险提示" items={report.narrative.risks} fallback="暂无额外风险提示" />
      </section>

      {!validation.is_valid && (
        <section className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-red-800">
          <h3 className="font-bold">事实校验失败</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {validation.errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </section>
      )}

      <footer className="mt-6 rounded-2xl bg-slate-50 p-4 text-xs leading-6 text-slate-500">
        <div>资产目录：{assets.root}</div>
        <div>HTML：{assets.html}</div>
        <div>PNG：{assets.png}</div>
      </footer>
    </article>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="border-l-4 border-slate-900 pl-3 text-lg font-black text-slate-950">{children}</h3>;
}

function Metric({ label, value, tone }: { label: string; value: string; tone: "red" | "green" | "slate" }) {
  const toneClass = {
    red: "text-red-600",
    green: "text-emerald-700",
    slate: "text-slate-950",
  }[tone];

  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <div className={`text-2xl font-black tabular-nums ${toneClass}`}>{value}</div>
      <div className="mt-1 text-xs font-medium text-slate-500">{label}</div>
    </div>
  );
}

function NarrativeBlock({ title, items, fallback }: { title: string; items: string[]; fallback: string }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <h3 className="text-sm font-bold text-slate-900">{title}</h3>
      {items.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-600">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm leading-6 text-slate-600">{fallback}</p>
      )}
    </div>
  );
}
