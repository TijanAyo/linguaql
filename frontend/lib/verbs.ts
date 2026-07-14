export type Phase = "ingest" | "query";

// Connect & Ingest — "Snooping & digging" + self-referential LingoQL nods.
export const ingestVerbs: string[] = [
  "Schema-sniffing",
  "Databasing",
  "Rummaging",
  "Foraging",
  "Spelunking",
  "Excavating",
  "Unearthing",
  "Prospecting",
  "Sleuthing",
  "Snuffling",
  "Snooping",
  "Nosing",
  "Delving",
  "Probing",
  "Fossicking",
  "Ferreting",
  "Beavering",
  "Squirreling",
  "Row-wrangling",
  "Table-talking",
];

// Ask / query — "Pondering & musing" + "A little magic" + LingoQL nods.
export const queryVerbs: string[] = [
  "Pondering",
  "Cogitating",
  "Noodling",
  "Ruminating",
  "Mulling",
  "Musing",
  "Ideating",
  "Percolating",
  "Marinating",
  "Brewing",
  "Simmering",
  "Bewitching",
  "Enchanting",
  "Alchemizing",
  "Concocting",
  "Conjuring",
  "Divining",
  "Steeping",
  "Query-whispering",
  "JOIN-juggling",
  "Word-herding",
  "Lingoing",
];

export function verbsFor(phase: Phase): string[] {
  return phase === "ingest" ? ingestVerbs : queryVerbs;
}

/** Fisher–Yates shuffle (returns a new array; never mutates the source). */
export function shuffle<T>(items: T[]): T[] {
  const out = items.slice();
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}
