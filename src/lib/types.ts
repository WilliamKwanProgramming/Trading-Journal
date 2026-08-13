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

export interface ConfidenceInterval {
  low: number;
  high: number;
}

export interface BootstrapAnalysis {
  sampleSize: number;
  resamples: number;
  observedExpectancy: number | null;
  meanExpectancy: number | null;
  medianExpectancy: number | null;
  confidence90: ConfidenceInterval | null;
  confidence95: ConfidenceInterval | null;
  probabilityPositive: number | null;
  probabilityNonPositive: number | null;
  validProfitFactorSamples: number;
  medianProfitFactor: number | null;
  profitFactorConfidence95: ConfidenceInterval | null;
  sharpeConfidence95: ConfidenceInterval | null;
}

export interface ProfitConcentration {
  largestWinnerGrossProfitShare: number | null;
  largestWinnerNetProfitShare: number | null;
  topTwoGrossProfitShare: number | null;
  topThreeGrossProfitShare: number | null;
  positiveProfitHhi: number | null;
}

export interface RobustnessAnalysis {
  minimumLeaveOneOutExpectancy: number | null;
  maximumLeaveOneOutExpectancy: number | null;
  averageLeaveOneOutExpectancy: number | null;
  expectancyStaysPositiveAfterAnyRemoval: boolean | null;
  expectancyExcludingLargestWinner: number | null;
  expectancyExcludingLargestLoser: number | null;
  expectancyExcludingBestAndWorst: number | null;
  winRateExcludingLargestWinner: number | null;
  profitFactorExcludingLargestWinner: number | null;
  profitFactorExcludingLargestLoser: number | null;
  trimmedExpectancy10: number | null;
  trimmedExpectancyAvailable: boolean;
  trimmedExpectancyNote: string;
  concentration: ProfitConcentration;
}

export interface ReturnDistribution {
  sampleSize: number;
  mean: number | null;
  median: number | null;
  meanMedianDifference: number | null;
  standardDeviation: number | null;
  downsideDeviation: number | null;
  variance: number | null;
  interquartileRange: number | null;
  medianAbsoluteDeviation: number | null;
  coefficientOfVariation: number | null;
}

export interface MonteCarloHorizon {
  horizon: number;
  probabilityPositive: number;
  probabilityNegative: number;
  endingReturn: ConfidenceInterval & { median: number; p25: number; p75: number };
  medianMaximumDrawdown: number;
  maximumDrawdown90: number;
  maximumDrawdown95: number;
}

export interface LosingStreakHorizon {
  horizon: number;
  expectedLongestStreak: number;
  medianLongestStreak: number;
  longestStreak90: number;
  longestStreak95: number;
  probabilityAtLeast2: number;
  probabilityAtLeast3: number;
  probabilityAtLeast5: number;
}

export interface WinRateUncertainty {
  wins: number;
  losses: number;
  observed: number | null;
  confidence90: ConfidenceInterval | null;
  confidence95: ConfidenceInterval | null;
}

export interface RiskAdjustedPerformance {
  sharpeTradeLevel: number | null;
  sortinoTradeLevel: number | null;
  downsideDeviation: number | null;
  recoveryFactor: number | null;
  convention: string;
}

export interface SubgroupStatistic {
  group: string;
  trades: number;
  winRate: number;
  meanReturn: number;
  medianReturn: number;
  totalPnlCad: number;
  profitFactor: number | null;
  averageWinner: number | null;
  averageLoser: number | null;
  expectancy: number;
}

export interface StatisticalEdge {
  sampleSize: number;
  sampleLabel: string;
  sampleWarning: string;
  observedExpectancy: number | null;
  breakEvenWinRate: number | null;
  observedWinRate: number | null;
  winRateMarginOfSafety: number | null;
  bootstrap: BootstrapAnalysis;
  robustness: RobustnessAnalysis;
  distribution: ReturnDistribution;
  riskAdjusted: RiskAdjustedPerformance;
  monteCarlo: MonteCarloHorizon[];
  losingStreaks: {
    current: number;
    historicalMaximum: number;
    horizons: LosingStreakHorizon[];
  };
  winRateUncertainty: WinRateUncertainty;
  riskOfRuin: {
    available: boolean;
    note: string;
  };
  maeMfe: {
    available: boolean;
    note: string;
  };
  subgroups: SubgroupStatistic[];
  subgroupNote: string;
  netRealizedPnlCad: number;
  maxDrawdownCad: number;
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
  statisticalEdge: StatisticalEdge;
  fxRate: FxRate | null;
  syncStatuses: SyncStatus[];
}
