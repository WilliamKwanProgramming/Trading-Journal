# Trade Ledger

A deliberately small Next.js trading journal for stocks and ETFs.

## Trading journal

```bash
npm install
npm run dev
```

Enter one execution at a time. Add another `BUY` to DCA or add to a position, and use `SELL` executions to reduce or close it. Currency is inferred from the Yahoo Finance ticker: `.TO`, `.V`, `.NE`, and `.CN` are CAD; other tickers are treated as USD.

The app pulls daily OHLC history and the USD/CAD exchange rate from Yahoo Finance's public chart endpoint. It caches the bars locally, converts monetary results to CAD, and uses the OHLC data to calculate marked P&L, max profit, max drawdown, win rate, profit factor, expectancy, and Kelly criterion. Individual share prices remain in their native quote currency. Yahoo Finance is a convenient free source, but it is not an official unlimited production API; refreshes can fail or be throttled, and the last cached data remains available.

The journal remains unchanged and is independent from the cycle workbench below.

## Cycle Analysis Workbench

The separate Streamlit app accepts one TradingView CSV and does not access the journal database or any external market-data API. Expected columns are `time`, `open`, `high`, `low`, and `close`; `Volume` is accepted but is not required. Extra TradingView indicator columns are ignored.

Create an isolated environment and launch it locally:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

The workbench includes:

- A local CSV library: uploaded files are saved under `data/csvs/`, restored when the app restarts, and removable from the sidebar's **Manage saved CSVs** panel.
- EMA and HP-filter detrending with an inspectable detrending length/HP cutoff.
- A harmonic-regression DFT baseline plus a separately selectable Goertzel DFT scan.
- Optional fractional periods and a clearly labelled Bartels-style persistence approximation.
- Fit, stability, separation, and optional genuineness filters.
- A latest-bar fixed composite whose full historical line and future projection use one final coefficient set.
- Historical and projected peak/trough lines drawn through both chart panels, with a chronological projected-turn list.
- Live recalculation and locked as-of models. A lock is only replaced when **Run analysis** is pressed in locked mode.
- A sidebar **Reset to default settings** control that clears the current analysis result and restores the documented defaults.
- Walk-forward comparisons across EMA/HP detrending, one/three/five-cycle models, and a seasonal-naive baseline.
- A separate **Rolling Trade Backtest** tab that refits the configured cycle model on every historical prefix, classifies the one-bar projection as bullish or bearish, reverses to the matching position on the next bar, and reports trades, equity, daily diagnostics, and cycle-selection stability. The earlier exact-turn rule remains available as a legacy comparison.
- CSV, JSON, Pine-ready text, PNG, and Markdown downloads.

### Methodology boundaries

This is a transparent public-method approximation inspired by the [FSC Cycle Scanner whitepaper](https://cycles.org/wp-content/uploads/2020/03/CycleScanner_Whitepaper_FSC.pdf), not a copy of Cycles.org software.

- Close to the public description: detrending before scanning, evaluation of every candidate period, single-frequency DFT/Goertzel analysis, recent-window amplitude and phase, validation for amplitude/phase persistence, strength as amplitude divided by period, and ranking of genuine/dominant cycles.
- Approximate: the HP lambda mapping, stability formula, rank weights, and Bartels-style genuineness calculation. The whitepaper describes these concepts but does not publish all tuned or proprietary formulas.
- Harmonic regression and Goertzel both evaluate a single DFT frequency. Harmonic least squares is retained as the baseline because it handles arbitrary non-bin periods and an intercept directly; the Goertzel recurrence is an explicit alternative.
- The composite is an oscillator/scenario, not a price target.

## Tests

```bash
pytest -q
```

The QQQ regression test automatically runs if a CSV with `QQQ` in its file name is present in the workspace. It otherwise skips with an explicit message because this repository did not include a QQQ fixture when the workbench was created.
