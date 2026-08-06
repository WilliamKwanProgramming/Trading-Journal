import { createTradeAction, refreshMarketDataAction } from "@/app/actions";
import { DeleteExecutionButton } from "@/components/delete-execution-button";
import Link from "next/link";
import type { Metrics, TradeCycle, TradeRow } from "@/lib/types";
import { getJournalData } from "@/lib/journal";

export const dynamic = "force-dynamic";

function money(value: number, currency = "USD") {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
}

function cadMoney(value: number, currency: "USD" | "CAD", usdCadRate: number | null) {
  return money(value * (currency === "USD" ? usdCadRate ?? 1 : 1), "CAD");
}

function pct(value: number | null, signed = false) {
  if (value === null) return "—";
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function date(value: string) {
  return new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="card stat"><div className="stat-label">{label}</div><div className="stat-value">{value}</div><div className="stat-detail">{detail}</div></div>;
}

function CycleRow({ cycle, usdCadRate }: { cycle: TradeCycle; usdCadRate: number | null }) {
  const pnlClass = cycle.totalPnl > 0 ? "positive" : cycle.totalPnl < 0 ? "negative" : "";
  return <tr>
    <td><Link className="cycle-link ticker" href={`/trades/${encodeURIComponent(cycle.id)}`}>{cycle.ticker}</Link><div className="ticker-sub">{cycle.executionCount} execution{cycle.executionCount === 1 ? "" : "s"} · {cycle.currency} · View details</div></td>
    <td>{date(cycle.startDate)}<br /><span className="ticker-sub">{cycle.endDate ? date(cycle.endDate) : "Still open"}</span></td>
    <td><span className={`pill ${cycle.closed ? "pill-closed" : "pill-open"}`}>{cycle.closed ? "CLOSED" : "OPEN"}</span></td>
    <td className={pnlClass}>{cadMoney(cycle.totalPnl, cycle.currency, usdCadRate)}<br /><span className="ticker-sub">{pct(cycle.returnPct, true)} · CAD</span></td>
    <td className="positive">{cadMoney(cycle.maxProfit, cycle.currency, usdCadRate)}</td>
    <td className="negative">{cadMoney(-cycle.maxDrawdown, cycle.currency, usdCadRate)}</td>
  </tr>;
}

function TradeRow({ trade }: { trade: TradeRow }) {
  return <tr>
    <td><div className="ticker">{trade.ticker}</div><div className="ticker-sub">{trade.currency}</div></td>
    <td>{date(trade.tradeDate)}</td>
    <td><span className={`pill ${trade.side === "BUY" ? "pill-buy" : "pill-sell"}`}>{trade.side}</span></td>
    <td>{trade.quantity.toLocaleString("en-CA")}</td>
    <td>{money(trade.price, trade.currency)}</td>
    <td><DeleteExecutionButton id={trade.id} /></td>
  </tr>;
}

function Metric({ name, value, help }: { name: string; value: string; help: string }) {
  return <div className="metric"><div className="metric-name">{name}</div><div className="metric-value">{value}</div><div className="metric-help">{help}</div></div>;
}

function metricsCopy(metrics: Metrics) {
  return metrics.closedTrades < 20 ? "Small sample — treat this as descriptive, not proof of an edge." : "Based on completed flat-to-flat trade cycles.";
}

export default function Home() {
  const data = getJournalData();
  const today = new Date().toISOString().slice(0, 10);
  const lastSync = data.syncStatuses[data.syncStatuses.length - 1];
  const usdCadRate = data.fxRate?.rate ?? null;

  return <div className="shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark">↗</div><div><div className="brand-name">Trade Ledger</div><div className="brand-sub">Multi-day journal · DCA-aware</div></div></div>
      <div className="top-actions"><span className="fx-rate"><strong>USD/CAD</strong> {usdCadRate === null ? "—" : usdCadRate.toFixed(4)}<small>{data.fxRate ? `Yahoo · ${date(data.fxRate.rateDate)}` : "Refresh to load"}</small></span><span className="sync-label">{lastSync ? `Yahoo sync ${new Date(lastSync.updatedAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "No market sync yet"}</span><form action={refreshMarketDataAction}><button className="button button-light" type="submit">Refresh prices</button></form></div>
    </header>

    <main className="main">
      <section className="intro"><div><div className="eyebrow">Your edge, in numbers</div><h1>Log the trade.<br />Let the journal do the math.</h1><p className="lede">Enter each buy and sell as it happens. Add another BUY whenever you DCA or add to a position; flat-to-flat cycles and daily OHLC data turn those executions into a clean review.</p></div><div className="data-note"><strong>Market data</strong><br />Yahoo Finance daily OHLC is pulled automatically for every ticker. Use Yahoo format for listings, such as <strong>SOXL.TO</strong> for the Canadian listing.</div></section>

      <div className="layout-grid">
        <aside className="card card-pad entry-card"><h2 className="card-title">Add an execution</h2><p className="card-kicker">Only the details that define a trade. Repeat BUYs for DCA.</p><form action={createTradeAction} className="form-stack">
          <div className="field"><label htmlFor="ticker">Ticker</label><input id="ticker" name="ticker" placeholder="SPY or SOXL.TO" autoCapitalize="characters" required /><span className="hint">Use the exact Yahoo Finance symbol.</span></div>
          <div className="field"><label htmlFor="tradeDate">Date</label><input id="tradeDate" name="tradeDate" type="date" defaultValue={today} required /></div>
          <div className="field"><label htmlFor="side">Action</label><select id="side" name="side" defaultValue="BUY"><option value="BUY">BUY — add / enter</option><option value="SELL">SELL — reduce / exit</option></select></div>
          <div className="field"><label htmlFor="quantity">Shares</label><input id="quantity" name="quantity" type="number" min="0.0001" step="0.0001" placeholder="100" required /></div>
          <div className="field"><label htmlFor="price">Price per share</label><input id="price" name="price" type="number" min="0.0001" step="0.0001" placeholder="125.50" required /></div>
          <button className="button button-primary form-submit" type="submit">Save execution</button>
        </form><p className="footer-note">Currency is inferred from the ticker suffix: .TO, .V, .NE and .CN are treated as CAD; everything else as USD.</p></aside>

        <div>
          <section className="stats"><Stat label="Total net P&L · CAD" value={money(data.metrics.netPnlCad, "CAD")} detail="Realized plus open marked P&L" /><Stat label="Trades" value={String(data.metrics.totalTrades)} detail={`${data.metrics.closedTrades} closed · ${data.metrics.totalExecutions} executions`} /><Stat label="Win rate" value={pct(data.metrics.winRate)} detail={`${data.metrics.wins} wins · ${data.metrics.losses} losses`} /><Stat label="Max drawdown · CAD" value={money(-data.metrics.maxDrawdownCad, "CAD")} detail="Largest peak-to-trough P&L" /></section>

          <section className="card section"><div className="section-head"><div><h2>Account metrics</h2><span>{metricsCopy(data.metrics)} All monetary values below are CAD.</span></div><span>{data.metrics.closedTrades} closed cycles</span></div><div className="metrics-grid"><Metric name="Average winner · CAD" value={data.metrics.averageWinnerCad === null ? "—" : money(data.metrics.averageWinnerCad, "CAD")} help="Average P&L on winning trade" /><Metric name="Average winner · %" value={pct(data.metrics.averageWinnerPct, true)} help="Average return on winning trade" /><Metric name="Average loser · CAD" value={data.metrics.averageLoserCad === null ? "—" : money(data.metrics.averageLoserCad, "CAD")} help="Average P&L on losing trade" /><Metric name="Average loser · %" value={pct(data.metrics.averageLoserPct)} help="Average return on losing trade" /><Metric name="Profit factor" value={data.metrics.profitFactor === null ? "—" : data.metrics.profitFactor.toFixed(2)} help="Gross winning P&L ÷ gross losing P&L" /><Metric name="Expectancy · CAD" value={data.metrics.expectancyCad === null ? "—" : money(data.metrics.expectancyCad, "CAD")} help="Average P&L per closed trade" /><Metric name="Expectancy · %" value={pct(data.metrics.expectancyPct, true)} help="Average return per closed trade" /><Metric name="Kelly criterion" value={pct(data.metrics.kellyPct, true)} help="Theoretical sizing edge" /><Metric name="Largest win · CAD" value={data.metrics.largestWinCad === null ? "—" : money(data.metrics.largestWinCad, "CAD")} help="Best completed trade" /><Metric name="Largest loss · CAD" value={data.metrics.largestLossCad === null ? "—" : money(data.metrics.largestLossCad, "CAD")} help="Worst completed trade" /><Metric name="Average holding days" value={data.metrics.averageHoldingDays === null ? "—" : data.metrics.averageHoldingDays.toFixed(1)} help="Calendar days for closed trades" /><Metric name="Average position size · CAD" value={data.metrics.averagePositionSizeCad === null ? "—" : money(data.metrics.averagePositionSizeCad, "CAD")} help="Average peak capital deployed per cycle" /></div></section>

          <section className="card section"><div className="section-head"><div><h2>Trade cycles</h2><span>DCA entries are grouped until the position returns to zero · CAD P&L</span></div><span>{data.cycles.length} total</span></div>{data.cycles.length ? <div className="table-wrap"><table><thead><tr><th>Ticker</th><th>Dates</th><th>Status</th><th>P&L · CAD</th><th>Max profit · CAD</th><th>Max drawdown · CAD</th></tr></thead><tbody>{data.cycles.map((cycle) => <CycleRow key={cycle.id} cycle={cycle} usdCadRate={usdCadRate} />)}</tbody></table></div> : <div className="empty">No trade cycles yet. Add your first BUY on the left and your journal will begin building a history.</div>}</section>

          <section className="card section"><div className="section-head"><div><h2>Open positions</h2><span>Latest available daily close · P&L and position size shown in CAD</span></div></div>{data.positions.length ? <div className="table-wrap"><table><thead><tr><th>Ticker</th><th>Shares</th><th>Position size · CAD</th><th>Avg entry · native</th><th>Last price · native</th><th>Unrealized P&L · CAD</th></tr></thead><tbody>{data.positions.map((position) => <tr key={position.ticker}><td><div className="ticker">{position.ticker}</div><div className="ticker-sub">{position.priceDate ? `Close ${date(position.priceDate)}` : "No price yet"}</div></td><td>{position.quantity.toLocaleString("en-CA")}</td><td>{money(position.positionSizeCad, "CAD")}</td><td>{money(position.averageEntry, position.currency)}</td><td>{position.lastPrice === null ? "—" : money(position.lastPrice, position.currency)}</td><td className={position.unrealizedPnl && position.unrealizedPnl < 0 ? "negative" : "positive"}>{position.unrealizedPnl === null ? "—" : cadMoney(position.unrealizedPnl, position.currency, usdCadRate)}</td></tr>)}</tbody></table></div> : <div className="empty">No open positions.</div>}</section>

          <section className="card section"><div className="section-head"><div><h2>Executions</h2><span>Every buy and sell you entered</span></div><span>{data.trades.length} rows</span></div>{data.trades.length ? <div className="table-wrap"><table><thead><tr><th>Ticker</th><th>Date</th><th>Action</th><th>Shares</th><th>Price</th><th></th></tr></thead><tbody>{data.trades.map((trade) => <TradeRow key={trade.id} trade={trade} />)}</tbody></table></div> : <div className="empty">Your execution ledger will appear here.</div>}</section>

          {data.syncStatuses.length ? <section className="section"><div className="status-list">{data.syncStatuses.map((status) => <span key={status.ticker} className={`status ${status.status === "ok" ? "status-ok" : "status-error"}`}>{status.ticker} · {status.message}</span>)}</div></section> : null}
        </div>
      </div>
    </main>
  </div>;
}
