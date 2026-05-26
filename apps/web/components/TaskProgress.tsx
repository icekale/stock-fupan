const stages = ["采集行情", "计算评分", "搜索新闻", "生成文案", "事实校验", "渲染导出"];

export function TaskProgress({ running, completed }: { running: boolean; completed: boolean }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-slate-950">生成进度</h2>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
          {completed ? "已完成" : running ? "运行中" : "待开始"}
        </span>
      </div>
      <div className="mt-4 grid gap-2">
        {stages.map((stage, index) => {
          const stageComplete = completed;
          const stageRunning = running && index === 0;

          return (
            <div key={stage} className="flex items-center justify-between rounded-2xl bg-slate-50 px-3 py-2.5">
              <span className="text-sm font-medium text-slate-700">{stage}</span>
              <span
                className={`text-xs font-semibold ${
                  stageComplete ? "text-emerald-700" : stageRunning ? "text-slate-950" : "text-slate-400"
                }`}
              >
                {stageComplete ? "完成" : stageRunning ? "运行中" : "待执行"}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
