const steps = ["生成报告", "系统校验", "人工修正", "预览长图", "导出归档"];

export function Stepper({ activeIndex }: { activeIndex: number }) {
  return (
    <ol className="grid gap-2 sm:grid-cols-5" aria-label="报告生成流程">
      {steps.map((step, index) => {
        const isActive = index === activeIndex;
        const isComplete = index < activeIndex;

        return (
          <li
            key={step}
            className={`rounded-2xl border px-3 py-3 text-sm transition-colors ${
              isActive
                ? "border-slate-900 bg-slate-900 text-white shadow-card"
                : isComplete
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : "border-slate-200 bg-white/80 text-slate-500"
            }`}
          >
            <div className="text-xs font-semibold tabular-nums opacity-70">0{index + 1}</div>
            <div className="mt-1 font-semibold">{step}</div>
          </li>
        );
      })}
    </ol>
  );
}
