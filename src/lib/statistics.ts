import type {
  BootstrapAnalysis,
  ConfidenceInterval,
  LosingStreakHorizon,
  MonteCarloHorizon,
  ReturnDistribution,
  RiskAdjustedPerformance,
  RobustnessAnalysis,
  StatisticalEdge,
  SubgroupStatistic,
  TradeCycle,
  WinRateUncertainty,
} from "@/lib/types";

const BOOTSTRAP_RESAMPLES = 50_000;
const MONTE_CARLO_PATHS = 50_000;
const MIN_TRIMMED_SAMPLE = 20;
const MIN_SUBGROUP_SAMPLE = 5;

function average(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function sorted(values: number[]) {
  return [...values].sort((a, b) => a - b);
}

function percentile(values: number[], probability: number) {
  if (!values.length) return null;
  const ordered = sorted(values);
  const position = (ordered.length - 1) * probability;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return ordered[lower];
  return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower);
}

function confidence(values: number[], probability: number): ConfidenceInterval | null {
  const tail = (1 - probability) / 2;
  const low = percentile(values, tail);
  const high = percentile(values, 1 - tail);
  return low === null || high === null ? null : { low, high };
}

function sampleVariance(values: number[]) {
  if (values.length < 2) return null;
  const mean = average(values) ?? 0;
  return values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
}

function sampleStandardDeviation(values: number[]) {
  const variance = sampleVariance(values);
  return variance === null ? null : Math.sqrt(variance);
}

function median(values: number[]) {
  return percentile(values, 0.5);
}

function profitFactor(values: number[]) {
  const grossProfit = values.filter((value) => value > 0).reduce((sum, value) => sum + value, 0);
  const grossLoss = Math.abs(values.filter((value) => value < 0).reduce((sum, value) => sum + value, 0));
  return grossLoss > 0 ? grossProfit / grossLoss : null;
}

function createRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4_294_967_296;
  };
}

function seedFromCycles(cycles: TradeCycle[]) {
  let seed = 0x1f123bb5;
  for (const cycle of cycles) {
    for (const character of cycle.id) seed = Math.imul(seed ^ character.charCodeAt(0), 16_777_619);
    seed = Math.imul(seed ^ Math.round(cycle.returnPct * 100), 16_777_619);
  }
  return seed >>> 0;
}

function sampleIndex(random: () => number, length: number) {
  return Math.min(length - 1, Math.floor(random() * length));
}

function bootstrapAnalysis(returns: number[], pnlCad: number[], seed: number): BootstrapAnalysis {
  const observedExpectancy = average(returns);
  if (!returns.length) {
    return {
      sampleSize: 0,
      resamples: BOOTSTRAP_RESAMPLES,
      observedExpectancy: null,
      meanExpectancy: null,
      medianExpectancy: null,
      confidence90: null,
      confidence95: null,
      probabilityPositive: null,
      probabilityNonPositive: null,
      validProfitFactorSamples: 0,
      medianProfitFactor: null,
      profitFactorConfidence95: null,
      sharpeConfidence95: null,
    };
  }

  const random = createRandom(seed);
  const expectancySamples: number[] = [];
  const profitFactorSamples: number[] = [];
  const sharpeSamples: number[] = [];

  for (let resample = 0; resample < BOOTSTRAP_RESAMPLES; resample += 1) {
    const sampledReturns: number[] = [];
    const sampledPnl: number[] = [];
    for (let index = 0; index < returns.length; index += 1) {
      const sampledIndex = sampleIndex(random, returns.length);
      sampledReturns.push(returns[sampledIndex]);
      sampledPnl.push(pnlCad[sampledIndex]);
    }
    const sampledMean = average(sampledReturns) ?? 0;
    expectancySamples.push(sampledMean);
    const sampledProfitFactor = profitFactor(sampledPnl);
    if (sampledProfitFactor !== null) profitFactorSamples.push(sampledProfitFactor);
    const sampledDeviation = sampleStandardDeviation(sampledReturns);
    if (sampledDeviation !== null && sampledDeviation > 0) sharpeSamples.push(sampledMean / sampledDeviation);
  }

  const positiveCount = expectancySamples.filter((value) => value > 0).length;
  return {
    sampleSize: returns.length,
    resamples: BOOTSTRAP_RESAMPLES,
    observedExpectancy,
    meanExpectancy: average(expectancySamples),
    medianExpectancy: median(expectancySamples),
    confidence90: confidence(expectancySamples, 0.9),
    confidence95: confidence(expectancySamples, 0.95),
    probabilityPositive: positiveCount / expectancySamples.length,
    probabilityNonPositive: (expectancySamples.length - positiveCount) / expectancySamples.length,
    validProfitFactorSamples: profitFactorSamples.length,
    medianProfitFactor: median(profitFactorSamples),
    profitFactorConfidence95: confidence(profitFactorSamples, 0.95),
    sharpeConfidence95: confidence(sharpeSamples, 0.95),
  };
}

function breakEvenWinRate(returns: number[]) {
  const winners = returns.filter((value) => value > 0);
  const losers = returns.filter((value) => value < 0).map((value) => Math.abs(value));
  const averageWinner = average(winners);
  const averageLoser = average(losers);
  if (averageWinner === null || averageLoser === null || averageWinner + averageLoser === 0) return null;
  return averageLoser / (averageWinner + averageLoser);
}

function removeIndex(values: number[], index: number) {
  return values.filter((_, valueIndex) => valueIndex !== index);
}

function indexOfLargest(values: number[], mode: "max" | "min") {
  if (!values.length) return -1;
  return values.reduce((bestIndex, value, index) => {
    if (mode === "max" && value > values[bestIndex]) return index;
    if (mode === "min" && value < values[bestIndex]) return index;
    return bestIndex;
  }, 0);
}

function trimmedMean(values: number[], trimFraction: number) {
  const trimCount = Math.floor(values.length * trimFraction);
  if (values.length < MIN_TRIMMED_SAMPLE || trimCount < 1 || values.length - (trimCount * 2) < 1) return null;
  return average(sorted(values).slice(trimCount, values.length - trimCount));
}

function robustnessAnalysis(returns: number[], pnlCad: number[]): RobustnessAnalysis {
  const leaveOneOut = returns.length > 1
    ? returns.map((_, index) => average(removeIndex(returns, index))).filter((value): value is number => value !== null)
    : [];
  const largestWinnerIndex = indexOfLargest(pnlCad, "max");
  const largestLoserIndex = indexOfLargest(pnlCad, "min");
  const largestWinnerRemovedReturns = largestWinnerIndex >= 0 ? removeIndex(returns, largestWinnerIndex) : [];
  const largestLoserRemovedReturns = largestLoserIndex >= 0 ? removeIndex(returns, largestLoserIndex) : [];
  const bestAndWorstRemovedReturns = largestWinnerIndex >= 0 && largestLoserIndex >= 0 && largestWinnerIndex !== largestLoserIndex
    ? returns.filter((_, index) => index !== largestWinnerIndex && index !== largestLoserIndex)
    : [];
  const grossProfit = pnlCad.filter((value) => value > 0).reduce((sum, value) => sum + value, 0);
  const positiveProfits = sorted(pnlCad.filter((value) => value > 0)).reverse();
  const netProfit = pnlCad.reduce((sum, value) => sum + value, 0);
  const winnerShares = positiveProfits.map((value) => value / grossProfit);

  return {
    minimumLeaveOneOutExpectancy: leaveOneOut.length ? Math.min(...leaveOneOut) : null,
    maximumLeaveOneOutExpectancy: leaveOneOut.length ? Math.max(...leaveOneOut) : null,
    averageLeaveOneOutExpectancy: average(leaveOneOut),
    expectancyStaysPositiveAfterAnyRemoval: leaveOneOut.length ? leaveOneOut.every((value) => value > 0) : null,
    expectancyExcludingLargestWinner: largestWinnerRemovedReturns.length ? average(largestWinnerRemovedReturns) : null,
    expectancyExcludingLargestLoser: largestLoserRemovedReturns.length ? average(largestLoserRemovedReturns) : null,
    expectancyExcludingBestAndWorst: bestAndWorstRemovedReturns.length ? average(bestAndWorstRemovedReturns) : null,
    winRateExcludingLargestWinner: largestWinnerRemovedReturns.length
      ? largestWinnerRemovedReturns.filter((value) => value > 0).length / largestWinnerRemovedReturns.length
      : null,
    profitFactorExcludingLargestWinner: largestWinnerIndex >= 0 ? profitFactor(removeIndex(pnlCad, largestWinnerIndex)) : null,
    profitFactorExcludingLargestLoser: largestLoserIndex >= 0 ? profitFactor(removeIndex(pnlCad, largestLoserIndex)) : null,
    trimmedExpectancy10: trimmedMean(returns, 0.1),
    trimmedExpectancyAvailable: trimmedMean(returns, 0.1) !== null,
    trimmedExpectancyNote: returns.length < MIN_TRIMMED_SAMPLE
      ? `N/A below ${MIN_TRIMMED_SAMPLE} closed trades; trimming would remove too much of the sample.`
      : "10% removed from each tail of the return distribution.",
    concentration: {
      largestWinnerGrossProfitShare: grossProfit > 0 && positiveProfits.length ? positiveProfits[0] / grossProfit : null,
      largestWinnerNetProfitShare: Math.abs(netProfit) > 0 && positiveProfits.length ? positiveProfits[0] / netProfit : null,
      topTwoGrossProfitShare: grossProfit > 0 ? positiveProfits.slice(0, 2).reduce((sum, value) => sum + value, 0) / grossProfit : null,
      topThreeGrossProfitShare: grossProfit > 0 ? positiveProfits.slice(0, 3).reduce((sum, value) => sum + value, 0) / grossProfit : null,
      positiveProfitHhi: winnerShares.length ? winnerShares.reduce((sum, share) => sum + share ** 2, 0) : null,
    },
  };
}

function returnDistribution(returns: number[]): ReturnDistribution {
  const mean = average(returns);
  const med = median(returns);
  const deviation = sampleStandardDeviation(returns);
  const variance = sampleVariance(returns);
  const downsideDeviation = returns.length
    ? Math.sqrt(returns.reduce((sum, value) => sum + Math.min(value, 0) ** 2, 0) / returns.length)
    : null;
  const returnMedian = med === null ? null : median(returns.map((value) => Math.abs(value - med)));
  const q25 = percentile(returns, 0.25);
  const q75 = percentile(returns, 0.75);

  return {
    sampleSize: returns.length,
    mean,
    median: med,
    meanMedianDifference: mean === null || med === null ? null : mean - med,
    standardDeviation: deviation,
    downsideDeviation,
    variance,
    interquartileRange: q25 === null || q75 === null ? null : q75 - q25,
    medianAbsoluteDeviation: returnMedian,
    coefficientOfVariation: mean !== null && deviation !== null && mean > 0 ? deviation / mean : null,
  };
}

function monteCarlo(returns: number[], seed: number): MonteCarloHorizon[] {
  const horizons = [20, 50, 100];
  if (!returns.length) return horizons.map((horizon) => ({
    horizon,
    probabilityPositive: 0,
    probabilityNegative: 0,
    endingReturn: { low: 0, p25: 0, median: 0, p75: 0, high: 0 },
    medianMaximumDrawdown: 0,
    maximumDrawdown90: 0,
    maximumDrawdown95: 0,
  }));

  return horizons.map((horizon, horizonIndex) => {
    const random = createRandom(seed + (horizonIndex * 0x9e3779b9));
    const endingReturns: number[] = [];
    const maximumDrawdowns: number[] = [];
    for (let path = 0; path < MONTE_CARLO_PATHS; path += 1) {
      let equity = 1;
      let peak = 1;
      let maximumDrawdown = 0;
      for (let trade = 0; trade < horizon; trade += 1) {
        equity *= 1 + returns[sampleIndex(random, returns.length)];
        if (equity > peak) peak = equity;
        if (peak > 0) maximumDrawdown = Math.max(maximumDrawdown, (peak - equity) / peak);
      }
      endingReturns.push(equity - 1);
      maximumDrawdowns.push(maximumDrawdown);
    }
    return {
      horizon,
      probabilityPositive: endingReturns.filter((value) => value > 0).length / endingReturns.length,
      probabilityNegative: endingReturns.filter((value) => value < 0).length / endingReturns.length,
      endingReturn: {
        low: percentile(endingReturns, 0.05) ?? 0,
        p25: percentile(endingReturns, 0.25) ?? 0,
        median: percentile(endingReturns, 0.5) ?? 0,
        p75: percentile(endingReturns, 0.75) ?? 0,
        high: percentile(endingReturns, 0.95) ?? 0,
      },
      medianMaximumDrawdown: percentile(maximumDrawdowns, 0.5) ?? 0,
      maximumDrawdown90: percentile(maximumDrawdowns, 0.9) ?? 0,
      maximumDrawdown95: percentile(maximumDrawdowns, 0.95) ?? 0,
    };
  });
}

function longestLosingStreak(returns: number[]) {
  let current = 0;
  let maximum = 0;
  for (const value of returns) {
    if (value < 0) {
      current += 1;
      maximum = Math.max(maximum, current);
    } else {
      current = 0;
    }
  }
  return { current, historicalMaximum: maximum };
}

function losingStreaks(chronologicalReturns: number[], seed: number) {
  const historical = longestLosingStreak(chronologicalReturns);
  const horizons = [20, 50, 100].map((horizon, horizonIndex): LosingStreakHorizon => {
    const random = createRandom(seed + 0x12345 + (horizonIndex * 0x517cc1b7));
    const longestStreaks: number[] = [];
    let atLeast2 = 0;
    let atLeast3 = 0;
    let atLeast5 = 0;
    for (let path = 0; path < MONTE_CARLO_PATHS; path += 1) {
      let current = 0;
      let maximum = 0;
      for (let trade = 0; trade < horizon; trade += 1) {
        if (chronologicalReturns[sampleIndex(random, chronologicalReturns.length)] < 0) {
          current += 1;
          maximum = Math.max(maximum, current);
        } else {
          current = 0;
        }
      }
      longestStreaks.push(maximum);
      if (maximum >= 2) atLeast2 += 1;
      if (maximum >= 3) atLeast3 += 1;
      if (maximum >= 5) atLeast5 += 1;
    }
    return {
      horizon,
      expectedLongestStreak: average(longestStreaks) ?? 0,
      medianLongestStreak: percentile(longestStreaks, 0.5) ?? 0,
      longestStreak90: percentile(longestStreaks, 0.9) ?? 0,
      longestStreak95: percentile(longestStreaks, 0.95) ?? 0,
      probabilityAtLeast2: atLeast2 / longestStreaks.length,
      probabilityAtLeast3: atLeast3 / longestStreaks.length,
      probabilityAtLeast5: atLeast5 / longestStreaks.length,
    };
  });
  return { ...historical, horizons };
}

function wilsonInterval(successes: number, trials: number, z: number): ConfidenceInterval | null {
  if (!trials) return null;
  const observed = successes / trials;
  const denominator = 1 + (z ** 2 / trials);
  const centre = (observed + (z ** 2 / (2 * trials))) / denominator;
  const margin = (z / denominator) * Math.sqrt((observed * (1 - observed) / trials) + (z ** 2 / (4 * trials ** 2)));
  return { low: Math.max(0, centre - margin), high: Math.min(1, centre + margin) };
}

function winRateUncertainty(returns: number[]): WinRateUncertainty {
  const wins = returns.filter((value) => value > 0).length;
  const losses = returns.filter((value) => value < 0).length;
  return {
    wins,
    losses,
    observed: returns.length ? wins / returns.length : null,
    confidence90: wilsonInterval(wins, returns.length, 1.645),
    confidence95: wilsonInterval(wins, returns.length, 1.96),
  };
}

function riskAdjusted(
  returns: number[],
  netRealizedPnlCad: number,
  maxDrawdownCad: number,
  bootstrap: BootstrapAnalysis,
): RiskAdjustedPerformance {
  const mean = average(returns);
  const deviation = sampleStandardDeviation(returns);
  const downsideDeviation = returns.length
    ? Math.sqrt(returns.reduce((sum, value) => sum + Math.min(value, 0) ** 2, 0) / returns.length)
    : null;
  return {
    sharpeTradeLevel: mean !== null && deviation !== null && deviation > 0 ? mean / deviation : null,
    sortinoTradeLevel: mean !== null && downsideDeviation !== null && downsideDeviation > 0 ? mean / downsideDeviation : null,
    downsideDeviation,
    recoveryFactor: maxDrawdownCad > 0 ? netRealizedPnlCad / maxDrawdownCad : null,
    convention: `Trade-level returns, risk-free rate 0%, no annualization. Bootstrap Sharpe interval uses ${bootstrap.sharpeConfidence95 ? "valid resamples" : "no valid resamples"}.`,
  };
}

function subgroupStatistics(cycles: TradeCycle[], usdCadRate: number): { groups: SubgroupStatistic[]; note: string } {
  const grouped = new Map<string, TradeCycle[]>();
  for (const cycle of cycles) grouped.set(cycle.ticker, [...(grouped.get(cycle.ticker) ?? []), cycle]);
  const groups: SubgroupStatistic[] = [];
  for (const [group, groupCycles] of grouped) {
    if (groupCycles.length < MIN_SUBGROUP_SAMPLE) continue;
    const returns = groupCycles.map((cycle) => cycle.returnPct / 100);
    const pnl = groupCycles.map((cycle) => cycle.realizedPnl * (cycle.currency === "USD" ? usdCadRate : 1));
    const winners = returns.filter((value) => value > 0);
    const losers = returns.filter((value) => value < 0);
    groups.push({
      group,
      trades: groupCycles.length,
      winRate: winners.length / groupCycles.length,
      meanReturn: average(returns) ?? 0,
      medianReturn: median(returns) ?? 0,
      totalPnlCad: pnl.reduce((sum, value) => sum + value, 0),
      profitFactor: profitFactor(pnl),
      averageWinner: average(winners),
      averageLoser: average(losers),
      expectancy: average(returns) ?? 0,
    });
  }
  return {
    groups,
    note: groups.length
      ? `Ticker groups with at least ${MIN_SUBGROUP_SAMPLE} closed cycles are shown. Other categorical fields are not present in the journal schema.`
      : `No subgroup has at least ${MIN_SUBGROUP_SAMPLE} closed cycles; subgroup output is withheld to avoid false precision. The journal currently provides ticker as its only categorical grouping field.`,
  };
}

export function buildStatisticalEdge(cycles: TradeCycle[], usdCadRate: number, maxDrawdownCad: number): StatisticalEdge {
  const closedCycles = cycles.filter((cycle) => cycle.closed).sort((a, b) => a.startDate.localeCompare(b.startDate));
  const returns = closedCycles.map((cycle) => cycle.returnPct / 100);
  const pnlCad = closedCycles.map((cycle) => cycle.realizedPnl * (cycle.currency === "USD" ? usdCadRate : 1));
  const observedExpectancy = average(returns);
  const observedWinRate = returns.length ? returns.filter((value) => value > 0).length / returns.length : null;
  const seed = seedFromCycles(closedCycles);
  const bootstrap = bootstrapAnalysis(returns, pnlCad, seed);
  const robustness = robustnessAnalysis(returns, pnlCad);
  const distribution = returnDistribution(returns);
  const netRealizedPnlCad = pnlCad.reduce((sum, value) => sum + value, 0);
  const riskAdjustedPerformance = riskAdjusted(returns, netRealizedPnlCad, maxDrawdownCad, bootstrap);
  const subgroup = subgroupStatistics(closedCycles, usdCadRate);
  const sampleSize = closedCycles.length;

  let sampleLabel = "No closed-trade sample";
  let sampleWarning = "No closed trades are available for statistical analysis.";
  if (sampleSize > 0 && sampleSize < 10) {
    sampleLabel = "Extremely small sample";
    sampleWarning = "Extremely small sample: estimates, intervals, and simulations are highly unstable and descriptive only.";
  } else if (sampleSize < 30) {
    sampleLabel = "Very limited evidence";
    sampleWarning = "Very limited evidence: use these results as exploratory diagnostics, not proof of a persistent edge.";
  } else if (sampleSize < 50) {
    sampleLabel = "Early sample";
    sampleWarning = "Early sample: statistical uncertainty remains material even where point estimates look strong.";
  } else if (sampleSize < 100) {
    sampleLabel = "Moderate sample";
    sampleWarning = "Moderate sample: estimates are more informative, but still depend on the observed trade distribution.";
  } else {
    sampleLabel = "More meaningful statistical history";
    sampleWarning = "Larger sample than the dashboard's descriptive bands; continue checking for regime and sizing changes.";
  }

  return {
    sampleSize,
    sampleLabel,
    sampleWarning,
    observedExpectancy,
    breakEvenWinRate: breakEvenWinRate(returns),
    observedWinRate,
    winRateMarginOfSafety: observedWinRate === null || breakEvenWinRate(returns) === null ? null : observedWinRate - (breakEvenWinRate(returns) ?? 0),
    bootstrap,
    robustness,
    distribution,
    riskAdjusted: riskAdjustedPerformance,
    monteCarlo: monteCarlo(returns, seed),
    losingStreaks: returns.length ? losingStreaks(returns, seed) : {
      current: 0,
      historicalMaximum: 0,
      horizons: [20, 50, 100].map((horizon) => ({
        horizon,
        expectedLongestStreak: 0,
        medianLongestStreak: 0,
        longestStreak90: 0,
        longestStreak95: 0,
        probabilityAtLeast2: 0,
        probabilityAtLeast3: 0,
        probabilityAtLeast5: 0,
      })),
    },
    winRateUncertainty: winRateUncertainty(returns),
    riskOfRuin: {
      available: false,
      note: "Unavailable: the journal stores cycle entry value and realized P&L, but not account equity or allocation as a share of total equity. Cycle returns cannot safely be treated as full-account returns.",
    },
    maeMfe: {
      available: false,
      note: "Unavailable: daily OHLC is available for cycle-level drawdown, but the raw journal has no trade-level intratrade mark-to-market path needed for MAE/MFE.",
    },
    subgroups: subgroup.groups,
    subgroupNote: subgroup.note,
    netRealizedPnlCad,
    maxDrawdownCad,
  };
}
