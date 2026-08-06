import Link from "next/link";
import { notFound } from "next/navigation";

import { DeleteExecutionButton } from "@/components/delete-execution-button";
import { getJournalData } from "@/lib/journal";
import type { TradeRow } from "@/lib/types";

export const dynamic = "force-dynamic";

function money(value: number, currency = "USD") {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

function cadMoney(value: number, currency: "USD" | "CAD", usdCadRate: number | null) {
  return money(value * (currency === "USD" ? usdCadRate ?? 1 : 1), "CAD");
}

function date(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function pct(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function DetailMetric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="metric"><div className="metric-name">{label}</div><div className="metric-value">{value}</div>{detail ? <div className="metric-help">{detail}</div> : null}</div>;
}

function ExecutionRow({ trade }: { trade: TradeRow }) {
  return <tr>
    <td>{date(trade.tradeDate)}</td>
    <td><span className={`pill ${trade.side === "BUY" ? "pill-buy" : "pill-sell"}`}>{trade.side}</span></td>
    <td>{trade.quantity.toLocaleString("en-CA")}</td>
    <td>{money(trade.price, trade.currency)}</td>
    <td>{money(trade.quantity * trade.price, trade.currency)}</td>
    <td><DeleteExecutionButton id={trade.id} /></td>
  </tr>;
}

export default async function TradeCyclePage({
  params,
}: {
  params: Promise<{ cycleId: string }>;
}) {
  const { cycleId } = await params;
  const data = getJournalData();
  const cycle = data.cycles.find((item) => item.id === decodeURIComponent(cycleId));
  if (!cycle) notFound();

  const usdCadRate = data.fxRate?.rate ?? null;
  const endDate = cycle.endDate ? date(cycle.endDate) : "Still open";

  return <div className="shell">
    <header className="topbar"><div className="brand"><div className="brand-mark">↗</div><div><div className="brand-name">Trade Ledger</div><div className="brand-sub">Trade cycle detail</div></div></div><Link className="button button-light" href="/">Back to journal</Link></header>
    <main className="main">
      <Link className="back-link" href="/">← Back to all trade cycles</Link>
      <section className="detail-hero"><div><div className="eyebrow">{cycle.closed ? "Closed trade cycle" : "Open trade cycle"}</div><h1>{cycle.ticker}</h1><p className="lede">{date(cycle.startDate)} → {endDate} · {cycle.executionCount} execution{cycle.executionCount === 1 ? "" : "s"} · {cycle.currency} prices</p></div><span className={`pill ${cycle.closed ? "pill-closed" : "pill-open"}`}>{cycle.closed ? "CLOSED" : "OPEN"}</span></section>
      <section className="card section"><div className="section-head"><div><h2>Cycle statistics</h2><span>Monetary results are converted to CAD using the saved USD/CAD rate.</span></div><span>{data.fxRate ? `USD/CAD ${data.fxRate.rate.toFixed(4)}` : "USD/CAD unavailable"}</span></div><div className="metrics-grid"><DetailMetric label="Total P&L · CAD" value={cadMoney(cycle.totalPnl, cycle.currency, usdCadRate)} /><DetailMetric label="Realized P&L · CAD" value={cadMoney(cycle.realizedPnl, cycle.currency, usdCadRate)} /><DetailMetric label="Unrealized P&L · CAD" value={cadMoney(cycle.unrealizedPnl, cycle.currency, usdCadRate)} /><DetailMetric label="Return" value={pct(cycle.returnPct)} /><DetailMetric label="Max profit · CAD" value={cadMoney(cycle.maxProfit, cycle.currency, usdCadRate)} /><DetailMetric label="Max drawdown · CAD" value={cadMoney(-cycle.maxDrawdown, cycle.currency, usdCadRate)} /><DetailMetric label="Holding days" value={String(cycle.holdingDays)} detail="Calendar days" /><DetailMetric label="Peak position · CAD" value={cadMoney(cycle.maxPositionValue, cycle.currency, usdCadRate)} detail="Largest capital deployed" /><DetailMetric label="Average entry" value={money(cycle.averageEntry, cycle.currency)} detail={`${cycle.quantity.toLocaleString("en-CA")} shares currently open`} /><DetailMetric label="Executions" value={String(cycle.executionCount)} /></div></section>
      <section className="card section"><div className="section-head"><div><h2>Executions in this cycle</h2><span>Delete an incorrect execution here and all cycle statistics will recalculate.</span></div><span>{cycle.executionCount} rows</span></div><div className="table-wrap"><table><thead><tr><th>Date</th><th>Action</th><th>Shares</th><th>Price · native</th><th>Notional · native</th><th></th></tr></thead><tbody>{cycle.trades.map((trade) => <ExecutionRow key={trade.id} trade={trade} />)}</tbody></table></div></section>
      <p className="footer-note">Max profit and max drawdown use the available daily OHLC history for {cycle.ticker}. If the listing has incomplete intraday high/low data, the journal falls back to the daily close rather than treating missing values as zero.</p>
    </main>
  </div>;
}
