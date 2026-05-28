export function getLatestTradeDate(now: Date = new Date()) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });
  const parts = formatter.formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const date = new Date(
    Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day)),
  );
  if (values.weekday === "Sun") {
    date.setUTCDate(date.getUTCDate() - 2);
  } else if (values.weekday === "Sat") {
    date.setUTCDate(date.getUTCDate() - 1);
  }
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
