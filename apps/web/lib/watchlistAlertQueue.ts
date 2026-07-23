import type { WatchlistAlertEvent } from "./types";

export type AlertSession = "morning" | "afternoon" | "close";

const severityRank: Record<WatchlistAlertEvent["severity"], number> = {
  high: 0,
  medium: 1,
  low: 2,
};

const sessionTypeRank: Record<AlertSession, Record<WatchlistAlertEvent["event_type"], number>> = {
  morning: { risk: 0, intraday: 1, opportunity: 2, plan: 3, stale_review: 4 },
  afternoon: { risk: 0, intraday: 1, opportunity: 2, plan: 3, stale_review: 4 },
  close: { risk: 0, stale_review: 1, plan: 2, opportunity: 3, intraday: 4 },
};

export function resolveAlertSession(now = new Date()): AlertSession {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? "0");
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? "0");
  const clock = hour * 60 + minute;

  if (clock >= 9 * 60 + 30 && clock < 11 * 60 + 30) return "morning";
  if (clock >= 13 * 60 && clock < 15 * 60) return "afternoon";
  return "close";
}

export function orderWatchlistAlerts(
  alerts: WatchlistAlertEvent[],
  session: AlertSession,
): WatchlistAlertEvent[] {
  return [...alerts].sort((left, right) => {
    const highRiskDiff = Number(isHighRisk(right)) - Number(isHighRisk(left));
    if (highRiskDiff !== 0) return highRiskDiff;

    const typeDiff = sessionTypeRank[session][left.event_type] - sessionTypeRank[session][right.event_type];
    if (typeDiff !== 0) return typeDiff;

    const severityDiff = severityRank[left.severity] - severityRank[right.severity];
    if (severityDiff !== 0) return severityDiff;

    return Date.parse(right.last_seen_at) - Date.parse(left.last_seen_at);
  });
}

export function alertSessionLabel(session: AlertSession): string {
  return { morning: "早盘", afternoon: "午后", close: "收盘复盘" }[session];
}

function isHighRisk(alert: WatchlistAlertEvent): boolean {
  return alert.event_type === "risk" && alert.severity === "high";
}
