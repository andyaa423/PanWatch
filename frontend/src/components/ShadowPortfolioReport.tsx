import { useEffect, useState } from 'react'
import { fetchAPI } from '@panwatch/api'
import BenchChart from '@/components/BenchChart'

type Summary = {
  empty: boolean
  curve: Array<{date:string; baseline:number; shadow:number; benchmark:number|null}>
  metrics: {total_return:number; max_drawdown:number; win_rate:number}
  baseline_metrics: {total_return:number; max_drawdown:number}
  coverage: {executed:number; pending:number}
}

const pct = (v:number) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`

export default function ShadowPortfolioReport() {
  const [data, setData] = useState<Summary | null>(null)
  useEffect(() => { fetchAPI<Summary>('/portfolio/shadow/summary').then(setData).catch(() => undefined) }, [])
  if (!data || data.empty) return null
  return <section className="mb-5 rounded-xl border border-border bg-card p-4">
    <div className="flex items-baseline justify-between gap-3"><h2 className="text-base font-semibold">AI 建议影子组合</h2><span className="text-xs text-muted-foreground">只读复盘，不会提交真实交易</span></div>
    <div className="mt-3 grid grid-cols-3 gap-3 text-sm"><div><p className="text-muted-foreground">原始持仓</p><b>{pct(data.baseline_metrics.total_return)}</b></div><div><p className="text-muted-foreground">AI 影子组合</p><b>{pct(data.metrics.total_return)}</b></div><div><p className="text-muted-foreground">最大回撤 / 胜率</p><b>{pct(-data.metrics.max_drawdown)} / {pct(data.metrics.win_rate)}</b></div></div>
    <div className="mt-3 flex gap-4 text-xs"><span>原始持仓</span><span className="text-primary">AI 影子组合</span><span className="text-muted-foreground">沪深300</span></div>
    {data.curve.filter(p => p.benchmark != null).length >= 2 && <BenchChart className="mt-2" curve={data.curve.filter((p): p is typeof p & {benchmark:number} => p.benchmark != null).map(p => ({date:p.date, portfolio:p.shadow, comparison:p.baseline, benchmark:p.benchmark}))} />}
    <p className="mt-2 text-xs text-muted-foreground">已执行 {data.coverage.executed} 条建议，待下一可交易价格执行 {data.coverage.pending} 条。</p>
  </section>
}
