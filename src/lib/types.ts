export const tradeSides = ["BUY", "SELL"] as const;
export type TradeSide = (typeof tradeSides)[number];
export type Currency = "USD" | "CAD";

export interface TradeRow {
  id: string;
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  tradeDate: string;
  currency: Currency;
  createdAt: string;
}

export interface MarketBar {
  ticker: string;
  barDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface TradeCycle {
  id: string;
  ticker: string;
  currency: Currency;
  startDate: string;
  endDate: string | null;
  closed: boolean;
  executionCount: number;
  entryValue: number;
  quantity: number;
  averageEntry: number;
  realizedPnl: number;
  unrealizedPnl: number;
  totalPnl: number;
  returnPct: number;
  maxProfit: number;
  maxDrawdown: number;
  holdingDays: number;
  maxPositionValue: number;
  trades: TradeRow[];
}

export interface Metrics {
  totalTrades: number;
  totalExecutions: number;
  closedTrades: number;
  wins: number;
  losses: number;
  breakeven: number;
  winRate: number | null;
  profitFactor: number | null;
  expectancyPct: number | null;
  averageWinnerPct: number | null;
  averageLoserPct: number | null;
  averageWinnerCad: number | null;
  averageLoserCad: number | null;
  expectancyCad: number | null;
  kellyPct: number | null;
  netPnlCad: number;
  realizedPnlCad: number;
  openMarkedPnlCad: number;
  grossProfitCad: number;
  grossLossCad: number;
  maxDrawdownCad: number;
  maxProfitCad: number;
  largestWinCad: number | null;
  largestLossCad: number | null;
  averageHoldingDays: number | null;
  averagePositionSizeCad: number | null;
}

export interface FxRate {
  pair: "USD/CAD";
  rate: number;
  rateDate: string;
  source: string;
  updatedAt: string;
}

export interface PositionSummary {
  ticker: string;
  currency: Currency;
  quantity: number;
  averageEntry: number;
  positionSizeCad: number;
  lastPrice: number | null;
  unrealizedPnl: number | null;
  priceDate: string | null;
}

export interface SyncStatus {
  ticker: string;
  status: "ok" | "error";
  message: string;
  updatedAt: string;
}

export interface JournalData {
  trades: TradeRow[];
  cycles: TradeCycle[];
  positions: PositionSummary[];
  metrics: Metrics;
  fxRate: FxRate | null;
  syncStatuses: SyncStatus[];
}
