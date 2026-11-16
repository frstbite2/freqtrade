import type { Metadata } from "next";
import { MarketsView } from "./markets-view";

export const metadata: Metadata = { title: "Markets" };

export default async function MarketsPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  return <MarketsView initialQuery={typeof q === "string" ? q.slice(0, 32) : ""} />;
}
