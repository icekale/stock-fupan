import type {
  ConfigStatusItem,
  DataSourceOptionsCurrent,
  DataSourceOptionsResponse,
} from "../lib/types";

const statusCopy: Record<ConfigStatusItem["status"], { label: string; dot: string; badge: string }> = {
  ready: {
    label: "已就绪",
    dot: "bg-emerald-500",
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  },
  missing_key: {
    label: "缺少 Key",
    dot: "bg-amber-500",
    badge: "bg-amber-50 text-amber-700 ring-amber-100",
  },
  disabled: {
    label: "未启用",
    dot: "bg-slate-300",
    badge: "bg-slate-100 text-slate-500 ring-slate-200",
  },
  local: {
    label: "本地",
    dot: "bg-sky-500",
    badge: "bg-sky-50 text-sky-700 ring-sky-100",
  },
  experimental: {
    label: "实验",
    dot: "bg-violet-500",
    badge: "bg-violet-50 text-violet-700 ring-violet-100",
  },
};

const unknownStatusCopy = {
  label: "未知",
  dot: "bg-slate-400",
  badge: "bg-slate-100 text-slate-600 ring-slate-200",
};

export function DataSourceStatusPanel({
  items,
  options,
  draft,
  saving,
  error,
  onDraftChange,
  onSave,
}: {
  items: ConfigStatusItem[];
  options: DataSourceOptionsResponse | null;
  draft: DataSourceOptionsCurrent | null;
  saving: boolean;
  error: string | null;
  onDraftChange: (draft: DataSourceOptionsCurrent) => void;
  onSave: () => void;
}) {
  return (
    <section id="sources" className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Data Sources</p>
          <h2 className="mt-1 text-xl font-black tracking-tight text-slate-950">数据源配置状态</h2>
        </div>
        <p className="text-sm text-slate-500">运行时配置保存到本地 SQLite，不显示 API Key 明文。</p>
      </div>

      {options && draft && (
        <div className="mt-4 space-y-4 rounded-2xl border border-slate-100 bg-slate-50 p-4">
          {options.categories.map((category) => (
            <fieldset key={category.key} className="space-y-2">
              <legend className="text-sm font-black text-slate-800">{category.label}</legend>
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {category.options.map((option) => {
                  const checked =
                    category.key === "review_sources"
                      ? draft.review_sources.includes(option.key)
                      : draft[category.key] === option.key;
                  return (
                    <label
                      key={`${category.key}-${option.key}`}
                      className={`flex min-h-20 cursor-pointer items-start gap-3 rounded-2xl border bg-white p-3 text-sm transition ${
                        checked ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <input
                        checked={checked}
                        className="mt-1 h-4 w-4 accent-slate-950"
                        name={category.key}
                        onChange={() => onDraftChange(updateDraft(draft, category.key, option.key))}
                        type={category.selection === "multiple" ? "checkbox" : "radio"}
                      />
                      <span className="min-w-0">
                        <span className="block font-black text-slate-950">{option.label}</span>
                        <span className="mt-1 block text-xs font-semibold text-slate-500">{option.role}</span>
                        <span className="mt-1 block text-xs leading-5 text-slate-500">{option.detail}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}

          <label className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-3">
            <span>
              <span className="block text-sm font-black text-slate-950">数据源失败时允许 fake 回退</span>
              <span className="mt-1 block text-xs text-slate-500">关闭后真实源失败会直接让报告生成失败。</span>
            </span>
            <input
              checked={draft.fallback_enabled}
              className="h-5 w-5 accent-slate-950"
              onChange={(event) => onDraftChange({ ...draft, fallback_enabled: event.target.checked })}
              type="checkbox"
            />
          </label>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs text-slate-500">
              {draft.updated_at ? `上次保存：${new Date(draft.updated_at).toLocaleString("zh-CN")}` : "当前使用环境变量默认配置"}
            </div>
            <button
              className="rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
              disabled={saving}
              onClick={onSave}
              type="button"
            >
              {saving ? "保存中" : "保存数据源选项"}
            </button>
          </div>
          {error && <p className="rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        </div>
      )}

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => {
          const view = statusCopy[item.status] ?? unknownStatusCopy;
          return (
            <article key={`${item.name}-${item.role}`} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${view.dot}`} aria-hidden="true" />
                    <h3 className="font-black text-slate-950">{item.name}</h3>
                  </div>
                  <p className="mt-1 text-xs font-semibold text-slate-500">{item.role}</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${view.badge}`}>
                  {view.label}
                </span>
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">{item.detail}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function updateDraft(
  draft: DataSourceOptionsCurrent,
  key: "market_provider" | "news_provider" | "review_sources",
  value: string,
): DataSourceOptionsCurrent {
  if (key === "review_sources") {
    return {
      ...draft,
      review_sources: draft.review_sources.includes(value)
        ? draft.review_sources.filter((item) => item !== value)
        : [...draft.review_sources, value],
    };
  }
  return { ...draft, [key]: value };
}
