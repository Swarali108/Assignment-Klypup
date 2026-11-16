/** NSE regular trading session (09:15 to 15:30 IST, Monday to Friday), closed on NSE trading holidays. */
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/**
 * NSE equity (CM segment) trading holidays that fall on weekdays, as published by NSE's holiday master
 * (https://www.nseindia.com/api/holiday-master?type=trading, key "CM"), read on 16 Nov 2026.
 * Weekend holidays are left out (the market is shut anyway). Refresh this list each December for the
 * next year; a day missing here is treated as a normal trading day.
 */
export const NSE_HOLIDAYS: Record<string, string> = {
  "2026-01-15": "Municipal Corporation Election - Maharashtra",
  "2026-01-26": "Republic Day",
  "2026-03-03": "Holi",
  "2026-03-26": "Shri Ram Navami",
  "2026-03-31": "Shri Mahavir Jayanti",
  "2026-04-03": "Good Friday",
  "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
  "2026-05-01": "Maharashtra Day",
  "2026-05-28": "Bakri Id",
  "2026-06-26": "Muharram",
  "2026-09-14": "Ganesh Chaturthi",
  "2026-10-02": "Mahatma Gandhi Jayanti",
  "2026-10-20": "Dussehra",
  "2026-11-10": "Diwali-Balipratipada",
  "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
  "2026-12-25": "Christmas",
};

/** "Monday, 16 November" for a local date. */
export function dayLabel(d: Date): string {
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS_LONG[d.getMonth()]}`;
}

/** The browser's local calendar day as YYYY-MM-DD. */
export function localDay(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function greetingFor(hour: number): string {
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

/** The wall-clock time in India as a Date whose local fields read IST, whatever the browser's own zone. */
function istClock(now: Date): Date {
  return new Date(now.getTime() + 330 * 60_000 + now.getTimezoneOffset() * 60_000);
}

/** True when NSE's regular session runs on this IST calendar day (a weekday that is not a holiday). */
function isTradingDay(ist: Date): boolean {
  const dow = ist.getDay();
  return dow >= 1 && dow <= 5 && !NSE_HOLIDAYS[localDay(ist)];
}

/** "tomorrow", "Wednesday" or "Monday 30 Nov": how to name the next trading day after an IST date. */
function nextOpenLabel(ist: Date): string {
  const day = new Date(ist.getFullYear(), ist.getMonth(), ist.getDate());
  for (let step = 1; step <= 14; step++) {
    day.setDate(day.getDate() + 1);
    if (!isTradingDay(day)) continue;
    if (step === 1) return "tomorrow";
    return step < 7 ? WEEKDAYS[day.getDay()] : `${WEEKDAYS[day.getDay()]} ${day.getDate()} ${MONTHS_LONG[day.getMonth()].slice(0, 3)}`;
  }
  return "next trading day";
}

export type MarketStatus = { open: boolean; label: string };

/** "Markets open · closes 15:30 IST" while the regular session runs; otherwise when it opens next,
 * naming the NSE holiday when today is one. */
export function marketStatus(now: Date): MarketStatus {
  const ist = istClock(now);
  const minutes = ist.getHours() * 60 + ist.getMinutes();
  const holiday = NSE_HOLIDAYS[localDay(ist)];
  if (isTradingDay(ist)) {
    if (minutes >= 9 * 60 + 15 && minutes < 15 * 60 + 30) return { open: true, label: "Markets open · closes 15:30 IST" };
    if (minutes < 9 * 60 + 15) return { open: false, label: "Markets closed · opens 09:15 IST" };
  }
  const why = holiday ? ` today for ${holiday}` : "";
  return { open: false, label: `Markets closed${why} · opens ${nextOpenLabel(ist)} 09:15 IST` };
}
