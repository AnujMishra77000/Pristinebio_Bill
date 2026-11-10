const INDIA_TIME_ZONE = "Asia/Kolkata";

export function invoiceNumberPrefix(invoiceDate: string, documentType: "sales" | "reagent" | "credit_note" = "sales"): string {
  const prefix = documentType === "credit_note" ? "PBPL/CN/" : "PBPL/";
  const match = /^(\d{4})-(\d{2})-\d{2}$/.exec(invoiceDate);
  if (!match) return prefix;
  const startYear = Number(match[1]) - (Number(match[2]) < 4 ? 1 : 0);
  return `${prefix}${startYear}-${String(startYear + 1).slice(-2)}/`;
}

export function indiaDateInputValue(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: INDIA_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}
