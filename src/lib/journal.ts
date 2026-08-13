import { randomUUID } from "node:crypto";
import { getDb } from "@/lib/db";
import type {
  Currency,
  FxRate,
  JournalData,
  MarketBar,
  Metrics,
  PositionSummary,
  SyncStatus,
  TradeCycle,
  TradeRow,
  TradeSide,
} from "@/lib/types";
import { buildStatisticalEdge } from "@/lib/statistics";

function nowIso() {
  return new Date().toISOString();
}

export function normalizeTicker(value: string) {
  return value.trim().toUpperCase().replace(/\s+/g, "");
}

export function inferCurrency(ticker: string): Currency {
  return /\.(TO|V|NE|CN)$/.test(ticker.toUpperCase()) ? "CAD" : "USD";
}

export function insertTrade(input: {
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  tradeDate: string;
}) {
  const ticker = normalizeTicker(input.ticker);
  const currency = inferCurrency(ticker);
  const db = getDb();
  db.prepare(
    `INSERT INTO trades (id, ticker, side, quantity, price, trade_date, currency, created_at)
     VALUES (@id, @ticker, @side, @quantity, @price, @tradeDate, @currency, @createdAt)`,
  ).run({
    id: randomUUID(),
    ticker,
    side: input.side,
    quantity: input.quantity,
    price: input.price,
    tradeDate: input.tradeDate,
    currency,
    createdAt: nowIso(),
  });
  return { ticker, currency };
}

export function getTrades(): TradeRow[] {
  return getDb()
    .prepare(
      `SELECT id, ticker, side, quantity, price, trade_date AS tradeDate,
              currency, created_at AS createdAt
       FROM trades ORDER BY trade_date ASC, created_at ASC`,
    )
    .all() as TradeRow[];
}

export function getMarketBars(tickers: string[]) {
  if (tickers.length === 0) return new Map<string, MarketBar[]>();
  const placeholders = tickers.map(() => "?").join(",");
  const rows = getDb()
    .prepare(
      `SELECT ticker, bar_date AS barDate, open, high, low, close, volume
       FROM market_bars WHERE ticker IN (${placeholders}) ORDER BY bar_date ASC`,
    )
    .all(...tickers) as MarketBar[];
  return rows.reduce((map, row) => {
    // Some Yahoo exchange feeds (notably .NE) return zero for OHLC while
    // still returning a valid close. Zero is missing data here, not a real
    // market price; using it would make max drawdown look like a total loss.
    const normalizedRow: MarketBar = {
      ...row,
      open: row.open > 0 ? row.open : row.close,
      high: row.high > 0 ? row.high : row.close,
      low: row.low > 0 ? row.low : row.close,
    };
    const values = map.get(normalizedRow.ticker) ?? [];
    values.push(normalizedRow);
    map.set(normalizedRow.ticker, values);
    return map;
  }, new Map<string, MarketBar[]>());
}

export function upsertMarketBars(ticker: string, bars: MarketBar[]) {
  const db = getDb();
  const statement = db.prepare(
    `INSERT INTO market_bars (ticker, bar_date, open, high, low, close, volume)
     VALUES (@ticker, @barDate, @open, @high, @low, @close, @volume)
     ON CONFLICT(ticker, bar_date) DO UPDATE SET
       open=excluded.open, high=excluded.high, low=excluded.low,
       close=excluded.close, volume=excluded.volume`,
  );
  const transaction = db.transaction((rows: MarketBar[]) => {
    for (const bar of rows) statement.run({ ...bar, ticker });
  });
  transaction(bars);
}

export function saveSyncStatus(status: SyncStatus) {
  getDb()
    .prepare(
      `INSERT INTO sync_status (ticker, status, message, updated_at)
       VALUES (@ticker, @status, @message, @updatedAt)
       ON CONFLICT(ticker) DO UPDATE SET status=excluded.status,
       message=excluded.message, updated_at=excluded.updated_at`,
    )
    .run({ ...status });
}

export function getSyncStatuses(): SyncStatus[] {
  return getDb()
    .prepare(
      `SELECT ticker, status, message, updated_at AS updatedAt
       FROM sync_status ORDER BY ticker ASC`,
    )
    .all() as SyncStatus[];
}

export function upsertFxRate(rate: FxRate) {
  getDb()
    .prepare(
      `INSERT INTO fx_rates (pair, rate, rate_date, source, updated_at)
       VALUES (@pair, @rate, @rateDate, @source, @updatedAt)
       ON CONFLICT(pair) DO UPDATE SET rate=excluded.rate,
       rate_date=excluded.rate_date, source=excluded.source,
       updated_at=excluded.updated_at`,
    )
    .run(rate);
}

export function getFxRate(): FxRate | null {
  return (
    getDb()
      .prepare(
        `SELECT pair, rate, rate_date AS rateDate, source, updated_at AS updatedAt
         FROM fx_rates WHERE pair = 'USD/CAD' LIMIT 1`,
      )
      .get() as FxRate | undefined
  ) ?? null;
}

function cycleStats(
  cycleTrades: TradeRow[],
  bars: MarketBar[],
  closed: boolean,
  endDate: string | null,
) {
  let quantity = 0;
  let averageEntry = 0;
  let realizedPnl = 0;
  let maxPositionValue = 0;
  const series: number[] = [0];
  const highSeries: number[] = [0];
  const lowSeries: number[] = [0];
  const lastDate = endDate ?? new Date().toISOString().slice(0, 10);
  const relevantBars = bars.filter(
    (bar) => bar.barDate >= cycleTrades[0].tradeDate && bar.barDate <= lastDate,
  );
  let tradeIndex = 0;

  const applyTrade = (trade: TradeRow) => {
    if (trade.side === "BUY") {
      averageEntry =
        quantity === 0
          ? trade.price
          : (quantity * averageEntry + trade.quantity * trade.price) /
            (quantity + trade.quantity);
      quantity += trade.quantity;
    } else {
      const closeQuantity = Math.min(quantity, trade.quantity);
      realizedPnl += closeQuantity * (trade.price - averageEntry);
      quantity -= closeQuantity;
      if (quantity === 0) averageEntry = 0;
    }
    maxPositionValue = Math.max(maxPositionValue, quantity * averageEntry);
  };

  for (const bar of relevantBars) {
    while (
      tradeIndex < cycleTrades.length &&
      cycleTrades[tradeIndex].tradeDate <= bar.barDate
    ) {
      applyTrade(cycleTrades[tradeIndex]);
      tradeIndex += 1;
    }
    series.push(realizedPnl + (bar.close - averageEntry) * quantity);
    highSeries.push(realizedPnl + (bar.high - averageEntry) * quantity);
    lowSeries.push(realizedPnl + (bar.low - averageEntry) * quantity);
  }

  while (tradeIndex < cycleTrades.length) {
    applyTrade(cycleTrades[tradeIndex]);
    tradeIndex += 1;
  }
  if (relevantBars.length === 0) {
    series.push(realizedPnl);
    highSeries.push(realizedPnl);
    lowSeries.push(realizedPnl);
  }

  // Include the realized result even if Yahoo has no bars for an exchange.
  const entryValue = cycleTrades
    .filter((trade) => trade.side === "BUY")
    .reduce((sum, trade) => sum + trade.quantity * trade.price, 0);
  const latestBarIncludesFinalTrade =
    relevantBars.length > 0 &&
    relevantBars[relevantBars.length - 1].barDate >= cycleTrades[cycleTrades.length - 1].tradeDate;
  const currentPnl = closed || !latestBarIncludesFinalTrade
    ? realizedPnl
    : series[series.length - 1] ?? realizedPnl;
  const peak = Math.max(0, ...highSeries);
  let maxDrawdown = 0;
  let runningPeak = 0;
  for (let index = 0; index < highSeries.length; index += 1) {
    runningPeak = Math.max(runningPeak, highSeries[index]);
    maxDrawdown = Math.max(maxDrawdown, runningPeak - lowSeries[index]);
  }

  return {
    entryValue,
    quantity,
    averageEntry,
    realizedPnl,
    unrealizedPnl: currentPnl - realizedPnl,
    totalPnl: currentPnl,
    returnPct: entryValue ? (currentPnl / entryValue) * 100 : 0,
    maxProfit: peak,
    maxDrawdown,
    maxPositionValue,
  };
}

function calendarDaysBetween(startDate: string, endDate: string | null) {
  const end = endDate ?? new Date().toISOString().slice(0, 10);
  return Math.max(
    0,
    Math.round(
      (new Date(`${end}T00:00:00Z`).getTime() -
        new Date(`${startDate}T00:00:00Z`).getTime()) /
        86_400_000,
    ),
  );
}

export function buildTradeCycles(
  trades: TradeRow[],
  barsByTicker: Map<string, MarketBar[]>,
): TradeCycle[] {
  const grouped = new Map<string, TradeRow[]>();
  for (const trade of trades) {
    const rows = grouped.get(trade.ticker) ?? [];
    rows.push(trade);
    grouped.set(trade.ticker, rows);
  }

  const cycles: TradeCycle[] = [];
  for (const [ticker, tickerTrades] of grouped) {
    let current: TradeRow[] = [];
    let openQuantity = 0;
    for (const trade of tickerTrades) {
      if (current.length === 0) current = [trade];
      else current.push(trade);
      openQuantity += trade.side === "BUY" ? trade.quantity : -trade.quantity;

      if (openQuantity <= 0) {
        const first = current[0];
        const stats = cycleStats(current, barsByTicker.get(ticker) ?? [], true, trade.tradeDate);
        cycles.push({
          id: `${ticker}-${first.id}`,
          ticker,
          currency: first.currency,
          startDate: first.tradeDate,
          endDate: trade.tradeDate,
          closed: true,
          executionCount: current.length,
          holdingDays: calendarDaysBetween(first.tradeDate, trade.tradeDate),
          ...stats,
          trades: current,
        });
        current = [];
        openQuantity = 0;
      }
    }
    if (current.length) {
      const first = current[0];
      const stats = cycleStats(current, barsByTicker.get(ticker) ?? [], false, null);
      cycles.push({
        id: `${ticker}-${first.id}`,
        ticker,
        currency: first.currency,
        startDate: first.tradeDate,
        endDate: null,
        closed: false,
        executionCount: current.length,
        holdingDays: calendarDaysBetween(first.tradeDate, null),
        ...stats,
        trades: current,
      });
    }
  }
  return cycles.sort((a, b) => b.startDate.localeCompare(a.startDate));
}

function average(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

export function buildMetrics(cycles: TradeCycle[], usdCadRate: number): Metrics {
  const closed = cycles.filter((cycle) => cycle.closed);
  const wins = closed.filter((cycle) => cycle.totalPnl > 0);
  const losses = closed.filter((cycle) => cycle.totalPnl < 0);
  const winnerReturns = wins.map((cycle) => cycle.returnPct);
  const loserReturns = losses.map((cycle) => Math.abs(cycle.returnPct));
  const inCad = (value: number, currency: Currency) =>
    currency === "USD" ? value * usdCadRate : value;
  const grossProfitCad = wins.reduce(
    (sum, cycle) => sum + inCad(cycle.totalPnl, cycle.currency),
    0,
  );
  const grossLossCad = Math.abs(
    losses.reduce(
      (sum, cycle) => sum + inCad(cycle.totalPnl, cycle.currency),
      0,
    ),
  );
  const netPnlCad = cycles
    .reduce((sum, cycle) => sum + inCad(cycle.totalPnl, cycle.currency), 0);
  const realizedPnlCad = cycles
    .reduce((sum, cycle) => sum + inCad(cycle.realizedPnl, cycle.currency), 0);
  const openMarkedPnlCad = cycles
    .reduce((sum, cycle) => sum + inCad(cycle.unrealizedPnl, cycle.currency), 0);
  const avgWin = average(winnerReturns);
  const avgLoss = average(loserReturns);
  const winnerCad = wins.map((cycle) => inCad(cycle.totalPnl, cycle.currency));
  const loserCad = losses.map((cycle) => inCad(cycle.totalPnl, cycle.currency));
  const winRate = closed.length ? (wins.length / closed.length) * 100 : null;
  const payoff = avgWin && avgLoss ? avgWin / avgLoss : null;
  const expectancyPct = average(closed.map((cycle) => cycle.returnPct));
  const expectancyCad = average(
    closed.map((cycle) => inCad(cycle.totalPnl, cycle.currency)),
  );

  return {
    totalTrades: cycles.length,
    totalExecutions: cycles.reduce((sum, cycle) => sum + cycle.executionCount, 0),
    closedTrades: closed.length,
    wins: wins.length,
    losses: losses.length,
    breakeven: closed.filter((cycle) => cycle.totalPnl === 0).length,
    winRate,
    profitFactor: grossLossCad ? grossProfitCad / grossLossCad : null,
    expectancyPct,
    averageWinnerPct: avgWin,
    averageLoserPct: avgLoss ? -avgLoss : null,
    averageWinnerCad: average(winnerCad),
    averageLoserCad: average(loserCad),
    expectancyCad,
    kellyPct: winRate !== null && payoff ? (winRate / 100 - (1 - winRate / 100) / payoff) * 100 : null,
    netPnlCad,
    realizedPnlCad,
    openMarkedPnlCad,
    grossProfitCad,
    grossLossCad,
    maxDrawdownCad: Math.max(
      0,
      ...cycles.map((cycle) => inCad(cycle.maxDrawdown, cycle.currency)),
    ),
    maxProfitCad: Math.max(
      0,
      ...cycles.map((cycle) => inCad(cycle.maxProfit, cycle.currency)),
    ),
    largestWinCad: winnerCad.length ? Math.max(...winnerCad) : null,
    largestLossCad: loserCad.length ? Math.min(...loserCad) : null,
    averageHoldingDays: average(closed.map((cycle) => cycle.holdingDays)),
    averagePositionSizeCad: average(
      cycles.map((cycle) => inCad(cycle.maxPositionValue, cycle.currency)),
    ),
  };
}

function buildPositions(
  cycles: TradeCycle[],
  barsByTicker: Map<string, MarketBar[]>,
  usdCadRate: number,
): PositionSummary[] {
  return cycles
    .filter((cycle) => !cycle.closed)
    .map((cycle) => {
      const bars = barsByTicker.get(cycle.ticker) ?? [];
      const last = bars.filter((bar) => bar.barDate >= cycle.startDate).at(-1) ?? null;
      return {
        ticker: cycle.ticker,
        currency: cycle.currency,
        quantity: cycle.quantity,
        averageEntry: cycle.averageEntry,
        positionSizeCad:
          cycle.quantity * cycle.averageEntry *
          (cycle.currency === "USD" ? usdCadRate : 1),
        lastPrice: last?.close ?? null,
        unrealizedPnl: last ? (last.close - cycle.averageEntry) * cycle.quantity : null,
        priceDate: last?.barDate ?? null,
      };
    });
}

export function getJournalData(): JournalData {
  const trades = getTrades();
  const fxRate = getFxRate();
  const barsByTicker = getMarketBars([...new Set(trades.map((trade) => trade.ticker))]);
  const cycles = buildTradeCycles(trades, barsByTicker);
  const metrics = buildMetrics(cycles, fxRate?.rate ?? 1);
  return {
    trades: [...trades].reverse(),
    cycles,
    positions: buildPositions(cycles, barsByTicker, fxRate?.rate ?? 1),
    metrics,
    statisticalEdge: buildStatisticalEdge(cycles, fxRate?.rate ?? 1, metrics.maxDrawdownCad),
    fxRate,
    syncStatuses: getSyncStatuses(),
  };
}
