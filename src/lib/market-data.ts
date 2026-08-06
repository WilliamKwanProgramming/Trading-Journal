import {
  getTrades,
  normalizeTicker,
  saveSyncStatus,
  upsertFxRate,
  upsertMarketBars,
} from "@/lib/journal";
import type { MarketBar } from "@/lib/types";

type YahooPayload = {
  chart?: {
    result?: Array<{
      timestamp?: number[];
      indicators?: {
        quote?: Array<{
          open?: Array<number | null>;
          high?: Array<number | null>;
          low?: Array<number | null>;
          close?: Array<number | null>;
          volume?: Array<number | null>;
        }>;
      };
    }>;
    error?: { description?: string } | null;
  };
};

function dateFromTimestamp(timestamp: number) {
  return new Date(timestamp * 1000).toISOString().slice(0, 10);
}

async function fetchYahooBars(ticker: string, startDate: string) {
  const start = Math.floor(new Date(`${startDate}T00:00:00Z`).getTime() / 1000);
  const end = Math.floor((Date.now() + 86_400_000) / 1000);
  const url = new URL(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}`);
  url.searchParams.set("period1", String(start));
  url.searchParams.set("period2", String(end));
  url.searchParams.set("interval", "1d");
  url.searchParams.set("events", "history");
  url.searchParams.set("includeAdjustedClose", "true");

  const response = await fetch(url, {
    cache: "no-store",
    headers: { "User-Agent": "Mozilla/5.0 TradingJournal/1.0" },
  });
  const payload = (await response.json()) as YahooPayload;
  if (!response.ok || payload.chart?.error) {
    throw new Error(payload.chart?.error?.description ?? `Yahoo Finance returned ${response.status}.`);
  }
  const result = payload.chart?.result?.[0];
  const quote = result?.indicators?.quote?.[0];
  if (!result?.timestamp?.length || !quote) throw new Error("No OHLC data was returned.");

  return result.timestamp.flatMap((timestamp, index): MarketBar[] => {
    const open = quote.open?.[index];
    const high = quote.high?.[index];
    const low = quote.low?.[index];
    const close = quote.close?.[index];
    if (![open, high, low, close].every((value) => typeof value === "number" && Number.isFinite(value))) {
      return [];
    }
    const safeOpen = open as number;
    const safeHigh = high as number;
    const safeLow = low as number;
    const safeClose = close as number;
    return [{
      ticker,
      barDate: dateFromTimestamp(timestamp),
      // A few Yahoo listings return zero OHLC values with a valid close.
      // Treat those fields as unavailable rather than as a real zero price.
      open: safeOpen > 0 ? safeOpen : safeClose,
      high: safeHigh > 0 ? safeHigh : safeClose,
      low: safeLow > 0 ? safeLow : safeClose,
      close: safeClose,
      volume: typeof quote.volume?.[index] === "number" ? quote.volume[index] as number : null,
    }];
  });
}

export async function refreshMarketData(tickers?: string[]) {
  const trades = getTrades();
  const requested = tickers?.length
    ? [...new Set(tickers.map(normalizeTicker))]
    : [...new Set(trades.map((trade) => trade.ticker))];
  const results: string[] = [];

  for (const ticker of requested) {
    const firstTrade = trades.find((trade) => trade.ticker === ticker);
    const startDate = firstTrade?.tradeDate ?? new Date(Date.now() - 31_536_000_000).toISOString().slice(0, 10);
    try {
      const bars = await fetchYahooBars(ticker, startDate);
      upsertMarketBars(ticker, bars);
      saveSyncStatus({ ticker, status: "ok", message: `${bars.length} daily bars loaded from Yahoo Finance.`, updatedAt: new Date().toISOString() });
      results.push(`${ticker}: ${bars.length} bars`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Market data request failed.";
      saveSyncStatus({ ticker, status: "error", message, updatedAt: new Date().toISOString() });
      results.push(`${ticker}: ${message}`);
    }
  }

  try {
    const fxBars = await fetchYahooBars(
      "CAD=X",
      new Date(Date.now() - 31_536_000_000).toISOString().slice(0, 10),
    );
    const latestFx = fxBars.at(-1);
    if (!latestFx) throw new Error("No USD/CAD rate was returned.");
    upsertFxRate({
      pair: "USD/CAD",
      rate: latestFx.close,
      rateDate: latestFx.barDate,
      source: "Yahoo Finance",
      updatedAt: new Date().toISOString(),
    });
  } catch (error) {
    results.push(`USD/CAD: ${error instanceof Error ? error.message : "Rate request failed."}`);
  }

  return results;
}
