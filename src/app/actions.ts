"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { getDb } from "@/lib/db";
import { getTrades, insertTrade, normalizeTicker } from "@/lib/journal";
import { refreshMarketData } from "@/lib/market-data";

const tradeSchema = z.object({
  ticker: z.string().trim().min(1, "Enter a Yahoo Finance ticker."),
  side: z.enum(["BUY", "SELL"]),
  quantity: z.coerce.number().positive("Quantity must be greater than zero."),
  price: z.coerce.number().positive("Price must be greater than zero."),
  tradeDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Enter a valid date."),
});

export async function createTradeAction(formData: FormData) {
  const parsed = tradeSchema.parse({
    ticker: formData.get("ticker"),
    side: formData.get("side"),
    quantity: formData.get("quantity"),
    price: formData.get("price"),
    tradeDate: formData.get("tradeDate"),
  });
  if (parsed.side === "SELL") {
    const openQuantity = getTrades()
      .filter((trade) => trade.ticker === normalizeTicker(parsed.ticker))
      .reduce((quantity, trade) => quantity + (trade.side === "BUY" ? trade.quantity : -trade.quantity), 0);
    if (parsed.quantity > openQuantity) {
      throw new Error(`Cannot sell ${parsed.quantity} shares; only ${openQuantity} are open.`);
    }
  }
  const { ticker } = insertTrade(parsed);
  await refreshMarketData([ticker]);
  revalidatePath("/");
}

export async function refreshMarketDataAction() {
  await refreshMarketData();
  revalidatePath("/");
}

export async function deleteTradeAction(formData: FormData) {
  const id = z.string().uuid().parse(formData.get("id"));
  const result = getDb().prepare("DELETE FROM trades WHERE id = ?").run(id);

  if (result.changes > 0) {
    revalidatePath("/");
    revalidatePath("/trades/[cycleId]", "page");
  }
}
