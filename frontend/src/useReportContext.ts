import { useEffect, useRef, useState } from "react";

export type ContextField = "contract" | "stage" | "period_start" | "period_end";
type Suggestion = {
  fields: Record<ContextField, {
    value: string | number | null;
    status: "found" | "missing" | "ambiguous" | "uncertain";
  }>;
};
const empty = { contract: "", stage: "", period_start: "", period_end: "" };
const hints = {
  found: "Из КФЗ — можно исправить",
  missing: "Не найдено — заполните вручную",
  ambiguous: "Неоднозначно — заполните вручную",
  uncertain: "Не удалось прочитать уверенно — заполните вручную",
};

export function useReportContext() {
  const [values, setValues] = useState(empty);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const edited = useRef(new Set<ContextField>());
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);

  const stop = () => {
    generation.current++;
    controller.current?.abort();
    setLoading(false);
  };
  useEffect(() => () => {
    generation.current++;
    controller.current?.abort();
  }, []);

  const change = (field: ContextField, value: string) => {
    edited.current.add(field);
    setValues((current) => ({ ...current, [field]: value }));
  };
  const inspect = async (file?: File) => {
    stop();
    const currentGeneration = generation.current;
    setSuggestion(null);
    setError("");
    // A different report clears old suggestions, while preserving manual edits.
    setValues((current) => Object.fromEntries(
      (Object.keys(empty) as ContextField[]).map((field) => [field, edited.current.has(field) ? current[field] : ""]),
    ) as typeof empty);
    if (!file) return;
    if (!/\.(pdf|png|jpe?g)$/i.test(file.name) || !file.size || file.size > 25 * 1024 * 1024) {
      setError("Для распознавания выберите непустой PDF, PNG или JPEG до 25 МБ.");
      return;
    }
    const request = new AbortController();
    controller.current = request;
    setLoading(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/reports/context", { method: "POST", body, signal: request.signal });
      if (!response.ok) throw new Error("Не удалось распознать параметры КФЗ. Заполните их вручную.");
      const result: Suggestion = await response.json();
      if (generation.current !== currentGeneration) return;
      setSuggestion(result);
      setValues((current) => Object.fromEntries(
        (Object.keys(empty) as ContextField[]).map((field) => [field,
          edited.current.has(field) ? current[field] : String(result.fields[field].value ?? ""),
        ]),
      ) as typeof empty);
    } catch {
      if (generation.current === currentGeneration) {
        setError("Не удалось распознать параметры КФЗ. Заполните их вручную.");
      }
    } finally {
      if (generation.current === currentGeneration) setLoading(false);
    }
  };

  const hint = (field: ContextField) => edited.current.has(field) || !suggestion
    ? "" : hints[suggestion.fields[field].status];
  return { values, change, inspect, stop, loading, error, hint, recognized: !!suggestion };
}
