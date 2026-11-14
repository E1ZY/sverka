import { useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { authFetch } from "./auth";

type Locator = { source?: string };
export type ReportExtraction = {
  contract?: string;
  needs_review?: boolean;
  report_values?: Record<string, string | null>;
  report_evidence?: Record<string, Locator>;
  cost_rows?: { stage: number; year: number; values: Record<string, string | null>; evidence?: Record<string, Locator> }[];
};
const totals = [
  ["0200", "Оплата труда"], ["0300", "Страховые взносы"],
  ["0800", "Общепроизводственные затраты"], ["0900", "Общехозяйственные затраты"],
  ["total", "Итого по строке КФЗ"],
];
const details = [
  ["4", "Материальные затраты"], ["7", "Основная заработная плата"],
  ["8", "Дополнительная заработная плата"], ["9", "Резерв отпусков и взносов"],
  ["12", "Взносы: основная заработная плата"], ["13", "Взносы: дополнительная заработная плата"],
  ["14", "Взносы: резерв отпусков"],
];

export function ReportValueEditor({ caseId, documentId, fact, stage, year, disabled, saving, onSaving, onSaved }: {
  caseId: string; documentId: string; fact?: ReportExtraction; stage: number; year: number;
  disabled: boolean; saving: boolean; onSaving: (value: boolean) => void; onSaved: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const row = fact?.cost_rows?.find(row => row.stage === stage && row.year === year);
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving || disabled) return;
    const form = new FormData(event.currentTarget);
    const confirm = form.get("confirm") === "on";
    const values: Record<string, string> = {};
    const cells: { year: number; column: string; amount: string }[] = [];
    for (const [code] of totals) {
      const amount = String(form.get("total-" + code) || "").trim();
      if (!amount && fact?.report_values?.[code] != null) {
        setError("Для исправления сохранённой суммы укажите новое значение. Удаление суммы не сохраняется.");
        return;
      }
      if (amount && (confirm || amount !== String(fact?.report_values?.[code] ?? ""))) values[code] = amount;
    }
    for (const [column] of details) {
      const amount = String(form.get("cell-" + column) || "").trim();
      if (!amount && row?.values[column] != null) {
        setError("Для исправления сохранённой суммы подкатегории укажите новое значение.");
        return;
      }
      if (amount && (confirm || amount !== String(row?.values[column] ?? ""))) cells.push({ year, column, amount });
    }
    const contract = String(form.get("contract") || "").trim();
    if (!contract && fact?.contract) {
      setError("Укажите номер договора из оригинала КФЗ.");
      return;
    }
    const changedContract = !!contract && (confirm || contract !== (fact?.contract || ""));
    if (!Object.keys(values).length && !cells.length && !changedContract) {
      setError("Введите нераспознанную сумму, измените значение или подтвердите заполненные данные по оригиналу.");
      return;
    }
    setError("");
    onSaving(true);
    try {
      const response = await authFetch(`/api/cases/${caseId}/documents/${documentId}/report-review`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_values: values, cost_cells: cells,
          ...(changedContract ? { contract } : {}), reason: String(form.get("reason") || "").trim() }),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(typeof body.detail === "string" ? body.detail : "Проверьте суммы и причину уточнения.");
      }
      await onSaved();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось сохранить уточнение.");
    } finally {
      onSaving(false);
    }
  };
  return <div className="report-value-editor">
    <p className="notice">Суммы КФЗ за {stage} этап, {year} год. Пустая ячейка означает отсутствие распознанного значения; ноль вводится явно.</p>
    <form className="review-form" onSubmit={submit}>
      <fieldset disabled={saving || disabled}>
        <legend>Суммы из оригинала, ₽</legend>
        {totals.map(([code, label]) => <label key={code}>
          {code === "total" ? "∑" : code} · {label}
          <input name={"total-" + code} inputMode="decimal" maxLength={64} defaultValue={fact?.report_values?.[code] ?? ""} placeholder="Не распознано" />
          {fact?.report_evidence?.[code]?.source === "manual" && <small>Уточнено пользователем</small>}
        </label>)}
        <details className="report-detail-fields">
          <summary>Подкатегории дерева затрат</summary>
          {details.map(([column, label]) => <label key={column}>
            Колонка {column} · {label}
            <input name={"cell-" + column} inputMode="decimal" maxLength={64} defaultValue={row?.values[column] ?? ""} placeholder="Не распознано" />
            {row?.evidence?.[column]?.source === "manual" && <small>Уточнено пользователем</small>}
          </label>)}
        </details>
        <label>Договор из КФЗ<input name="contract" maxLength={80} defaultValue={fact?.contract || ""} placeholder="Номер договора из оригинала" /></label>
        <label className="report-confirm"><input type="checkbox" name="confirm" />Также подтверждаю все заполненные значения по оригиналу</label>
        <label>Причина уточнения<textarea name="reason" minLength={5} maxLength={1000} required placeholder="Например: сумма прочитана по оригиналу КФЗ" /></label>
      </fieldset>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="button primary full" disabled={saving || disabled}>
        {saving ? <Loader2 size={16} className="spin" /> : <Check size={16} />}Сохранить и пересчитать
      </button>
      <small>Нераспознанные поля можно оставить пустыми. Итоги не вычисляются из соседних ячеек. Исходное распознавание и прежний отчёт сохраняются в истории.</small>
    </form>
  </div>;
}
