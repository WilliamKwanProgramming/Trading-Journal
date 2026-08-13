import type {
  ConfidenceInterval,
  MonteCarloHorizon,
  StatisticalEdge,
} from "@/lib/types";

function percentage(value: number | null, digits = 1, signed = false) {
  if (value === null || !Number.isFinite(value)) return "N/A";
  const formatted = (value * 100).toFixed(digits);
  return `${signed && value > 0 ? "+" : ""}${formatted}%`;
}

function interval(value: ConfidenceInterval | null, digits = 1) {
  if (!value) return "N/A";
  return `[${percentage(value.low, digits, true)}, ${percentage(value.high, digits, true)}]`;
}

function numericInterval(value: ConfidenceInterval | null, digits = 2) {
  if (!value) return "N/A";
  return `[${number(value.low, digits)}, ${number(value.high, digits)}]`;
}

function money(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "N/A";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 }).format(value);
}

function number(value: number | null, digits = 2) {
  if (value === null || !Number.isFinite(value)) return "N/A";
  return value.toFixed(digits);
}

function ratio(value: number | null, digits = 2) {
  if (value === null || !Number.isFinite(value)) return "N/A";
  return value.toFixed(digits);
}

function AnalysisMetric({ label, value, help }: { label: string; value: string; help?: string }) {
  return <div className="analysis-metric"><div className="metric-name">{label}</div><div className="metric-value">{value}</div>{help ? <div className="metric-help">{help}</div> : null}</div>;
}

function AnalysisBlock({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return <section className="analysis-block"><div className="analysis-block-head"><h3>{title}</h3>{description ? <span>{description}</span> : null}</div>{children}</section>;
}

function horizon(data: StatisticalEdge, horizon: number) {
  return data.monteCarlo.find((item) => item.horizon === horizon) as MonteCarloHorizon;
}

function MonteCarloTable({ data }: { data: StatisticalEdge }) {
  return <div className="table-wrap"><table className="analysis-table"><thead><tr><th>Horizon</th><th>Profitable</th><th>Negative</th><th>5th percentile</th><th>25th percentile</th><th>Median</th><th>75th percentile</th><th>95th percentile</th></tr></thead><tbody>{data.monteCarlo.map((item) => <tr key={item.horizon}><td>{item.horizon} trades</td><td>{percentage(item.probabilityPositive)}</td><td>{percentage(item.probabilityNegative)}</td><td>{percentage(item.endingReturn.low, 1, true)}</td><td>{percentage(item.endingReturn.p25, 1, true)}</td><td>{percentage(item.endingReturn.median, 1, true)}</td><td>{percentage(item.endingReturn.p75, 1, true)}</td><td>{percentage(item.endingReturn.high, 1, true)}</td></tr>)}</tbody></table></div>;
}

export function StatisticalEdge({ data }: { data: StatisticalEdge }) {
  const fifty = horizon(data, 50);
  const breakEven = data.breakEvenWinRate;
  const concentration = data.robustness.concentration;

  return <section className="statistical-edge card section">
    <div className="section-head"><div><h2>Statistical Edge</h2><span>Closed-cycle returns · {data.bootstrap.resamples.toLocaleString("en-CA")} deterministic empirical resamples</span></div><span>{data.sampleSize} observations · {data.sampleLabel}</span></div>
    <div className="statistical-warning"><strong>{data.sampleWarning}</strong> These outputs describe uncertainty conditional on the observed closed trades; they are not proof that the strategy will remain profitable.</div>

    <div className="analysis-primary-grid">
      <AnalysisMetric label="Observed expectancy" value={percentage(data.observedExpectancy, 2, true)} help={`${data.sampleSize} closed trades`} />
      <AnalysisMetric label="Median trade return" value={percentage(data.distribution.median, 2, true)} help="Typical closed-trade return" />
      <AnalysisMetric label="Bootstrap 95% expectancy interval" value={interval(data.bootstrap.confidence95, 2)} help="Non-parametric percentile interval" />
      <AnalysisMetric label="Bootstrap P(expectancy > 0)" value={percentage(data.bootstrap.probabilityPositive)} help="Estimate from observed trade distribution" />
      <AnalysisMetric label="Break-even win rate" value={percentage(breakEven)} help="Based on average winner and loser returns" />
      <AnalysisMetric label="Win-rate 95% interval" value={interval(data.winRateUncertainty.confidence95)} help={`${data.winRateUncertainty.wins} wins · ${data.winRateUncertainty.losses} losses`} />
      <AnalysisMetric label="Expectancy excluding largest winner" value={percentage(data.robustness.expectancyExcludingLargestWinner, 2, true)} help="Leave-one-trade-out robustness check" />
      <AnalysisMetric label="Largest winner / gross profit" value={percentage(concentration.largestWinnerGrossProfitShare)} help="Profit concentration" />
      <AnalysisMetric label="Recovery factor" value={ratio(data.riskAdjusted.recoveryFactor)} help="Net realized P&L ÷ maximum drawdown" />
      <AnalysisMetric label="50-trade profitable probability" value={percentage(fifty?.probabilityPositive ?? null)} help="Empirical resampling simulation" />
      <AnalysisMetric label="50-trade median max drawdown" value={percentage(fifty?.medianMaximumDrawdown, 1)} help="Compounded normalized return path" />
      <AnalysisMetric label="50-trade 95th percentile drawdown" value={percentage(fifty?.maximumDrawdown95, 1)} help="Compounded normalized return path" />
    </div>

    <AnalysisBlock title="Bootstrap analysis" description="50,000 samples with replacement; each sample contains the observed number of closed trades.">
      <div className="analysis-grid"><AnalysisMetric label="Observed expectancy" value={percentage(data.bootstrap.observedExpectancy, 2, true)} /><AnalysisMetric label="Bootstrap mean expectancy" value={percentage(data.bootstrap.meanExpectancy, 2, true)} /><AnalysisMetric label="Bootstrap median expectancy" value={percentage(data.bootstrap.medianExpectancy, 2, true)} /><AnalysisMetric label="90% interval" value={interval(data.bootstrap.confidence90, 2)} /><AnalysisMetric label="95% interval" value={interval(data.bootstrap.confidence95, 2)} /><AnalysisMetric label="P(expectancy > 0)" value={percentage(data.bootstrap.probabilityPositive)} /><AnalysisMetric label="P(expectancy ≤ 0)" value={percentage(data.bootstrap.probabilityNonPositive)} /><AnalysisMetric label="Observations / resamples" value={`${data.bootstrap.sampleSize} / ${data.bootstrap.resamples.toLocaleString("en-CA")}`} /></div>
      <p className="analysis-note">The bootstrap probabilities estimate how often resampled means from this observed distribution are positive or non-positive. They are not literal certainty probabilities for the future strategy.</p>
    </AnalysisBlock>

    <AnalysisBlock title="Robustness and outlier sensitivity" description="Leave-one-out and trimmed-return checks show how much individual trades influence the result.">
      <div className="analysis-grid"><AnalysisMetric label="Minimum leave-one-out expectancy" value={percentage(data.robustness.minimumLeaveOneOutExpectancy, 2, true)} /><AnalysisMetric label="Maximum leave-one-out expectancy" value={percentage(data.robustness.maximumLeaveOneOutExpectancy, 2, true)} /><AnalysisMetric label="Average leave-one-out expectancy" value={percentage(data.robustness.averageLeaveOneOutExpectancy, 2, true)} /><AnalysisMetric label="Positive after any one removal" value={data.robustness.expectancyStaysPositiveAfterAnyRemoval === null ? "N/A" : data.robustness.expectancyStaysPositiveAfterAnyRemoval ? "Yes" : "No"} /><AnalysisMetric label="Excluding largest loser" value={percentage(data.robustness.expectancyExcludingLargestLoser, 2, true)} /><AnalysisMetric label="Excluding best and worst" value={percentage(data.robustness.expectancyExcludingBestAndWorst, 2, true)} /><AnalysisMetric label="Win rate excluding best" value={percentage(data.robustness.winRateExcludingLargestWinner)} /><AnalysisMetric label="PF excluding best winner" value={ratio(data.robustness.profitFactorExcludingLargestWinner)} /><AnalysisMetric label="PF excluding largest loser" value={ratio(data.robustness.profitFactorExcludingLargestLoser)} /><AnalysisMetric label="10% trimmed expectancy" value={percentage(data.robustness.trimmedExpectancy10, 2, true)} help={data.robustness.trimmedExpectancyNote} /></div>
    </AnalysisBlock>

    <AnalysisBlock title="Profit concentration" description="Only positive realized CAD P&L is included in the HHI calculation.">
      <div className="analysis-grid"><AnalysisMetric label="Largest winner / gross profit" value={percentage(concentration.largestWinnerGrossProfitShare)} /><AnalysisMetric label="Largest winner / net realized P&L" value={percentage(concentration.largestWinnerNetProfitShare)} /><AnalysisMetric label="Top 2 winners / gross profit" value={percentage(concentration.topTwoGrossProfitShare)} /><AnalysisMetric label="Top 3 winners / gross profit" value={percentage(concentration.topThreeGrossProfitShare)} /><AnalysisMetric label="Positive-profit HHI" value={ratio(concentration.positiveProfitHhi)} help="Higher means more concentrated" /><AnalysisMetric label="Net realized P&L" value={money(data.netRealizedPnlCad)} /></div>
    </AnalysisBlock>

    <AnalysisBlock title="Monte Carlo outcomes" description="Empirical resampling simulations conditional on the observed closed-trade return distribution; returns are compounded.">
      <MonteCarloTable data={data} />
      <div className="analysis-grid analysis-grid-spaced">{data.monteCarlo.map((item) => <AnalysisMetric key={item.horizon} label={`${item.horizon}-trade drawdown distribution`} value={`Median ${percentage(item.medianMaximumDrawdown)} · P90 ${percentage(item.maximumDrawdown90)} · P95 ${percentage(item.maximumDrawdown95)}`} />)}</div>
    </AnalysisBlock>

    <AnalysisBlock title="Losing-streak probabilities" description="A loss is a closed trade with a negative return; a win or break-even trade resets the streak.">
      <div className="analysis-grid"><AnalysisMetric label="Current losing streak" value={String(data.losingStreaks.current)} /><AnalysisMetric label="Maximum historical losing streak" value={String(data.losingStreaks.historicalMaximum)} /></div>
      <div className="table-wrap"><table className="analysis-table"><thead><tr><th>Horizon</th><th>Expected longest</th><th>Median longest</th><th>P90 longest</th><th>P95 longest</th><th>P(at least 2)</th><th>P(at least 3)</th><th>P(at least 5)</th></tr></thead><tbody>{data.losingStreaks.horizons.map((item) => <tr key={item.horizon}><td>{item.horizon} trades</td><td>{number(item.expectedLongestStreak, 1)}</td><td>{number(item.medianLongestStreak, 0)}</td><td>{number(item.longestStreak90, 0)}</td><td>{number(item.longestStreak95, 0)}</td><td>{percentage(item.probabilityAtLeast2)}</td><td>{percentage(item.probabilityAtLeast3)}</td><td>{percentage(item.probabilityAtLeast5)}</td></tr>)}</tbody></table></div>
    </AnalysisBlock>

    <AnalysisBlock title="Return distribution" description={`${data.distribution.sampleSize} closed-trade percentage returns; standard deviation and variance use sample denominators.`}>
      <div className="analysis-grid"><AnalysisMetric label="Mean return" value={percentage(data.distribution.mean, 2, true)} /><AnalysisMetric label="Median return" value={percentage(data.distribution.median, 2, true)} /><AnalysisMetric label="Mean − median" value={percentage(data.distribution.meanMedianDifference, 2, true)} /><AnalysisMetric label="Standard deviation" value={percentage(data.distribution.standardDeviation, 2)} /><AnalysisMetric label="Downside deviation" value={percentage(data.distribution.downsideDeviation, 2)} help="Root mean squared shortfall below 0%" /><AnalysisMetric label="Variance" value={number(data.distribution.variance, 5)} /><AnalysisMetric label="Interquartile range" value={percentage(data.distribution.interquartileRange, 2)} /><AnalysisMetric label="Median absolute deviation" value={percentage(data.distribution.medianAbsoluteDeviation, 2)} /><AnalysisMetric label="Coefficient of variation" value={ratio(data.distribution.coefficientOfVariation)} help="Shown only when positive mean is stable enough" /></div>
    </AnalysisBlock>

    <AnalysisBlock title="Risk-adjusted performance" description="Trade-level ratios are deliberately unannualized because these are multi-day cycles with different holding periods.">
      <div className="analysis-grid"><AnalysisMetric label="Trade-level Sharpe" value={ratio(data.riskAdjusted.sharpeTradeLevel)} /><AnalysisMetric label="Trade-level Sortino" value={ratio(data.riskAdjusted.sortinoTradeLevel)} /><AnalysisMetric label="Downside deviation" value={percentage(data.riskAdjusted.downsideDeviation, 2)} /><AnalysisMetric label="Recovery factor" value={ratio(data.riskAdjusted.recoveryFactor)} /><AnalysisMetric label="Bootstrap Sharpe 95% interval" value={numericInterval(data.bootstrap.sharpeConfidence95, 2)} /><AnalysisMetric label="Bootstrap PF median" value={ratio(data.bootstrap.medianProfitFactor)} /><AnalysisMetric label="Bootstrap PF 95% interval" value={numericInterval(data.bootstrap.profitFactorConfidence95, 2)} /></div>
      <p className="analysis-note">{data.riskAdjusted.convention} Profit-factor bootstrap samples with no losing trades are excluded rather than treated as valid infinity.</p>
    </AnalysisBlock>

    <AnalysisBlock title="Win-rate uncertainty" description="Wilson score intervals avoid the naive normal approximation for small samples.">
      <div className="analysis-grid"><AnalysisMetric label="Wins" value={String(data.winRateUncertainty.wins)} /><AnalysisMetric label="Losses" value={String(data.winRateUncertainty.losses)} /><AnalysisMetric label="Observed win rate" value={percentage(data.winRateUncertainty.observed)} /><AnalysisMetric label="90% Wilson interval" value={interval(data.winRateUncertainty.confidence90)} /><AnalysisMetric label="95% Wilson interval" value={interval(data.winRateUncertainty.confidence95)} /><AnalysisMetric label="Break-even win rate" value={percentage(data.breakEvenWinRate)} /><AnalysisMetric label="Win-rate margin of safety" value={percentage(data.winRateMarginOfSafety, 1, true)} /></div>
    </AnalysisBlock>

    <AnalysisBlock title="Risk of ruin and MAE / MFE" description="Unavailable outputs are intentionally not fabricated from insufficient source data.">
      <div className="analysis-unavailable"><strong>Risk of ruin / drawdown-threshold probabilities:</strong> {data.riskOfRuin.note}</div>
      <div className="analysis-unavailable"><strong>MAE / MFE:</strong> {data.maeMfe.note}</div>
    </AnalysisBlock>

    <AnalysisBlock title="Performance by subgroup" description="Subgroups are withheld when their sample is too small for a useful comparison.">
      {data.subgroups.length ? <div className="table-wrap"><table className="analysis-table"><thead><tr><th>Ticker</th><th>Trades</th><th>Win rate</th><th>Mean return</th><th>Median return</th><th>Total P&L</th><th>PF</th><th>Avg winner</th><th>Avg loser</th><th>Expectancy</th></tr></thead><tbody>{data.subgroups.map((group) => <tr key={group.group}><td>{group.group}</td><td>{group.trades}</td><td>{percentage(group.winRate)}</td><td>{percentage(group.meanReturn, 2, true)}</td><td>{percentage(group.medianReturn, 2, true)}</td><td>{money(group.totalPnlCad)}</td><td>{ratio(group.profitFactor)}</td><td>{percentage(group.averageWinner, 2, true)}</td><td>{percentage(group.averageLoser, 2, true)}</td><td>{percentage(group.expectancy, 2, true)}</td></tr>)}</tbody></table></div> : <div className="analysis-unavailable">{data.subgroupNote}</div>}
      {data.subgroups.length ? <p className="analysis-note">{data.subgroupNote}</p> : null}
    </AnalysisBlock>
  </section>;
}
