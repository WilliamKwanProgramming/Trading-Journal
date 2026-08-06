import Database from "better-sqlite3";
import path from "node:path";

const dbPath = path.join(process.cwd(), "data", "trading-journal.db");
const db = new Database(dbPath);

const knownExchangeSuffixes = new Set([
  "US",
  "TO",
  "TSX",
  "TSXV",
  "V",
  "NEO",
  "NEOE",
  "NASDAQ",
  "NYSE",
  "AMEX",
  "ARCA",
  "BATS",
]);

function normalizeSymbol(value) {
  return String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "");
}

function normalizeExchangeCode(value) {
  return String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "");
}

function splitTickerInput(symbol, exchangeCode = "") {
  const normalizedSymbol = normalizeSymbol(symbol);
  const normalizedExchangeCode = normalizeExchangeCode(exchangeCode);

  if (!normalizedSymbol.includes(".")) {
    return {
      symbol: normalizedSymbol,
      exchangeCode: normalizedExchangeCode,
    };
  }

  const parts = normalizedSymbol.split(".").filter(Boolean);
  if (parts.length < 2) {
    return {
      symbol: normalizedSymbol,
      exchangeCode: normalizedExchangeCode,
    };
  }

  const suffix = parts.at(-1) ?? "";
  const baseSymbol = parts.slice(0, -1).join(".");

  if (!knownExchangeSuffixes.has(suffix)) {
    return {
      symbol: normalizedSymbol,
      exchangeCode: normalizedExchangeCode,
    };
  }

  if (!normalizedExchangeCode || normalizedExchangeCode === suffix) {
    return {
      symbol: baseSymbol,
      exchangeCode: suffix,
    };
  }

  return {
    symbol: baseSymbol,
    exchangeCode: normalizedExchangeCode,
  };
}

function makeInstrumentKey(symbol, exchangeCode) {
  const parsed = splitTickerInput(symbol, exchangeCode);
  return `${normalizeSymbol(parsed.symbol)}.${normalizeExchangeCode(parsed.exchangeCode)}`;
}

function chooseDisplayName(currentValue, nextValue) {
  const current = String(currentValue ?? "").trim();
  const next = String(nextValue ?? "").trim();

  if (!current) return next;
  if (!next) return current;
  return current.length >= next.length ? current : next;
}

const malformedProfiles = db
  .prepare(
    `
      SELECT
        instrument_key AS instrumentKey,
        symbol,
        exchange_code AS exchangeCode,
        display_name AS displayName,
        currency,
        exposure_bias AS exposureBias,
        leverage_multiplier AS leverageMultiplier,
        notes,
        created_at AS createdAt,
        updated_at AS updatedAt
      FROM instrument_profiles
      WHERE symbol LIKE '%.%' OR instrument_key LIKE '%.TO.TO' OR instrument_key LIKE '%.US.US' OR instrument_key LIKE '%.NEO.NEO'
    `,
  )
  .all();

if (!malformedProfiles.length) {
  console.log("No malformed ticker rows found.");
  process.exit(0);
}

const cleanup = db.transaction(() => {
  const migrated = [];

  for (const profile of malformedProfiles) {
    const parsed = splitTickerInput(profile.symbol, profile.exchangeCode);
    const nextKey = makeInstrumentKey(parsed.symbol, parsed.exchangeCode);

    if (nextKey === profile.instrumentKey) {
      continue;
    }

    const existingTarget = db
      .prepare(
        `
          SELECT
            instrument_key AS instrumentKey,
            display_name AS displayName,
            currency,
            exposure_bias AS exposureBias,
            leverage_multiplier AS leverageMultiplier,
            notes,
            created_at AS createdAt,
            updated_at AS updatedAt
          FROM instrument_profiles
          WHERE instrument_key = ?
          LIMIT 1
        `,
      )
      .get(nextKey);

    db.prepare(
      `
        INSERT INTO instrument_profiles (
          instrument_key,
          symbol,
          exchange_code,
          display_name,
          currency,
          exposure_bias,
          leverage_multiplier,
          notes,
          created_at,
          updated_at
        ) VALUES (
          @instrumentKey,
          @symbol,
          @exchangeCode,
          @displayName,
          @currency,
          @exposureBias,
          @leverageMultiplier,
          @notes,
          @createdAt,
          @updatedAt
        )
        ON CONFLICT(instrument_key) DO UPDATE SET
          display_name = excluded.display_name,
          currency = excluded.currency,
          exposure_bias = excluded.exposure_bias,
          leverage_multiplier = excluded.leverage_multiplier,
          notes = excluded.notes,
          updated_at = excluded.updated_at
      `,
    ).run({
      instrumentKey: nextKey,
      symbol: parsed.symbol,
      exchangeCode: parsed.exchangeCode,
      displayName: chooseDisplayName(existingTarget?.displayName, profile.displayName),
      currency: existingTarget?.currency ?? profile.currency,
      exposureBias: existingTarget?.exposureBias ?? profile.exposureBias,
      leverageMultiplier:
        existingTarget?.leverageMultiplier ?? profile.leverageMultiplier,
      notes: chooseDisplayName(existingTarget?.notes, profile.notes),
      createdAt: existingTarget?.createdAt ?? profile.createdAt,
      updatedAt:
        new Date(
          Math.max(
            Date.parse(existingTarget?.updatedAt ?? profile.updatedAt),
            Date.parse(profile.updatedAt),
          ),
        ).toISOString(),
    });

    db.prepare(
      `
        UPDATE executions
        SET
          instrument_key = @nextKey,
          symbol = @symbol,
          exchange_code = @exchangeCode
        WHERE instrument_key = @oldKey
      `,
    ).run({
      nextKey,
      symbol: parsed.symbol,
      exchangeCode: parsed.exchangeCode,
      oldKey: profile.instrumentKey,
    });

    const stalePrices = db
      .prepare(
        `
          SELECT
            instrument_key AS instrumentKey,
            symbol,
            exchange_code AS exchangeCode,
            currency,
            close,
            previous_close AS previousClose,
            price_date AS priceDate,
            source,
            updated_at AS updatedAt
          FROM market_prices
          WHERE instrument_key = ?
        `,
      )
      .all(profile.instrumentKey);

    for (const price of stalePrices) {
      db.prepare(
        `
          INSERT INTO market_prices (
            instrument_key,
            symbol,
            exchange_code,
            currency,
            close,
            previous_close,
            price_date,
            source,
            updated_at
          ) VALUES (
            @instrumentKey,
            @symbol,
            @exchangeCode,
            @currency,
            @close,
            @previousClose,
            @priceDate,
            @source,
            @updatedAt
          )
          ON CONFLICT(instrument_key) DO UPDATE SET
            symbol = excluded.symbol,
            exchange_code = excluded.exchange_code,
            currency = excluded.currency,
            close = excluded.close,
            previous_close = excluded.previous_close,
            price_date = excluded.price_date,
            source = excluded.source,
            updated_at = excluded.updated_at
        `,
      ).run({
        ...price,
        instrumentKey: nextKey,
        symbol: parsed.symbol,
        exchangeCode: parsed.exchangeCode,
      });
    }

    const staleSnapshots = db
      .prepare(
        `
          SELECT
            snapshot_date AS snapshotDate,
            instrument_key AS instrumentKey,
            symbol,
            exchange_code AS exchangeCode,
            display_name AS displayName,
            currency,
            quantity,
            open_pnl AS openPnl,
            market_value AS marketValue,
            realized_pnl_all_time AS realizedPnlAllTime,
            exposure_bias AS exposureBias,
            leverage_multiplier AS leverageMultiplier,
            exposure_cad AS exposureCad,
            updated_at AS updatedAt
          FROM position_pnl_snapshots
          WHERE instrument_key = ?
        `,
      )
      .all(profile.instrumentKey);

    for (const snapshot of staleSnapshots) {
      db.prepare(
        `
          INSERT INTO position_pnl_snapshots (
            snapshot_date,
            instrument_key,
            symbol,
            exchange_code,
            display_name,
            currency,
            quantity,
            open_pnl,
            market_value,
            realized_pnl_all_time,
            exposure_bias,
            leverage_multiplier,
            exposure_cad,
            updated_at
          ) VALUES (
            @snapshotDate,
            @instrumentKey,
            @symbol,
            @exchangeCode,
            @displayName,
            @currency,
            @quantity,
            @openPnl,
            @marketValue,
            @realizedPnlAllTime,
            @exposureBias,
            @leverageMultiplier,
            @exposureCad,
            @updatedAt
          )
          ON CONFLICT(snapshot_date, instrument_key) DO UPDATE SET
            symbol = excluded.symbol,
            exchange_code = excluded.exchange_code,
            display_name = excluded.display_name,
            currency = excluded.currency,
            quantity = excluded.quantity,
            open_pnl = excluded.open_pnl,
            market_value = excluded.market_value,
            realized_pnl_all_time = excluded.realized_pnl_all_time,
            exposure_bias = excluded.exposure_bias,
            leverage_multiplier = excluded.leverage_multiplier,
            exposure_cad = excluded.exposure_cad,
            updated_at = excluded.updated_at
        `,
      ).run({
        ...snapshot,
        instrumentKey: nextKey,
        symbol: parsed.symbol,
        exchangeCode: parsed.exchangeCode,
      });
    }

    db.prepare("DELETE FROM market_prices WHERE instrument_key = ?").run(
      profile.instrumentKey,
    );
    db.prepare(
      "DELETE FROM position_pnl_snapshots WHERE instrument_key = ?",
    ).run(profile.instrumentKey);
    db.prepare("DELETE FROM instrument_profiles WHERE instrument_key = ?").run(
      profile.instrumentKey,
    );

    migrated.push({
      from: profile.instrumentKey,
      to: nextKey,
    });
  }

  return migrated;
});

const migrated = cleanup();

console.log(`Cleaned ${migrated.length} malformed ticker profile(s).`);
for (const row of migrated) {
  console.log(`${row.from} -> ${row.to}`);
}
