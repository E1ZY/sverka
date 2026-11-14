export function formatDuration(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  if (seconds > 0 && seconds < 1) return "< 1 с";
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return [hours ? `${hours} ч` : "", hours || minutes ? `${minutes} мин` : "", `${remainder} с`]
    .filter(Boolean).join(" ");
}
