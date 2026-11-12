import { CheckCheck, ChevronRight, CircleAlert, Loader2 } from "lucide-react";
import { useState } from "react";

type BatchItem = {
  fixture_id: string;
  title: string;
  known_limitation: string | null;
  case_id: string | null;
  run_id: string | null;
  status: string;
  progress: number;
  message: string;
  differences: number;
};

export type FixtureBatch = {
  id: string;
  status: "running" | "completed";
  total: number;
  done: number;
  progress: number;
  counts: {
    passed: number;
    known_limitations: number;
    failed: number;
    errors: number;
    unexpected_passes: number;
    queued: number;
    running: number;
  };
  items: BatchItem[];
};

const batchLabels: Record<string, string> = {
  queued: "В очереди",
  running: "Выполняется",
  passed: "Совпало с эталоном",
  known_limitation: "Ограничение MVP",
  failed: "Отличается от эталона",
  error: "Ошибка выполнения",
  unexpected_pass: "Ограничение не воспроизвелось",
};

export function FixtureBatchResults({
  batch,
  onOpen,
}: {
  batch: FixtureBatch;
  onOpen: (id: string) => void;
}) {
  const running = batch.status === "running";
  const [filter, setFilter] = useState("all");
  const visible = batch.items.filter(
    (item) =>
      filter === "all" ||
      (filter === "errors"
        ? ["error", "failed"].includes(item.status)
        : filter === "known"
          ? item.status === "known_limitation"
          : item.status === "unexpected_pass"),
  );
  return (
    <div className="fixture-batch-panel">
      <div className="fixture-batch-overview" role="status" aria-live="polite">
        <div className="fixture-batch-heading">
          <h3>{running ? "Проверяем все примеры" : "Проверка всех примеров завершена"}</h3>
          <span>
            {batch.done} из {batch.total} · {batch.progress}%
          </span>
        </div>
        <progress
          aria-label="Прогресс проверки всех примеров"
          value={batch.done}
          max={batch.total}
        />
        <div className="fixture-batch-counts">
          <span className="passed">
            <strong>{batch.counts.passed}</strong>Совпали с эталоном
          </span>
          <span className="known_limitation">
            <strong>{batch.counts.known_limitations}</strong>Ограничения MVP
          </span>
          <span
            className={batch.counts.failed + batch.counts.errors ? "error" : ""}
          >
            <strong>{batch.counts.failed + batch.counts.errors}</strong>Новые
            ошибки
          </span>
          {batch.counts.unexpected_passes > 0 && (
            <span className="unexpected_pass">
              <strong>{batch.counts.unexpected_passes}</strong>
              Ограничения не воспроизвелись
            </span>
          )}
        </div>
        <p>
          {running
            ? "Проверка продолжится, если закрыть окно. Результаты сохраняются автоматически."
            : "Откройте пример, чтобы посмотреть расчёт, источники и отличия от эталона."}
        </p>
      </div>
      <div className="suite-filters filters" aria-label="Фильтр результатов примеров">
        {[
          ["all", `Все (${batch.total})`],
          [
            "errors",
            `Новые ошибки (${batch.counts.errors + batch.counts.failed})`,
          ],
          ["known", `Ограничения (${batch.counts.known_limitations})`],
          ...(batch.counts.unexpected_passes
            ? [
                [
                  "fixed",
                  `Не воспроизвелись (${batch.counts.unexpected_passes})`,
                ],
              ]
            : []),
        ].map(([value, label]) => (
          <button
            key={value}
            className={filter === value ? "active" : ""}
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        className="fixture-batch-list"
        aria-label="Результаты проверки примеров"
      >
        {!visible.length && (
          <div className="empty-small">
            <CheckCheck size={25} />
            <p>
              {running
                ? "В этой группе пока нет результатов. Проверка продолжается."
                : filter === "errors"
                  ? "Новых ошибок нет"
                  : "В этой группе нет примеров"}
            </p>
          </div>
        )}
        {visible.map((item) => (
          <div
            className={"fixture-batch-row " + item.status}
            key={item.fixture_id}
          >
            <span className="fixture-batch-icon">
              {item.status === "running" ? (
                <Loader2 size={19} className="spin" />
              ) : item.status === "passed" ||
                item.status === "unexpected_pass" ? (
                <CheckCheck size={19} />
              ) : item.status === "queued" ? (
                <span className="batch-queued-dot" />
              ) : (
                <CircleAlert size={19} />
              )}
            </span>
            <div className="fixture-batch-item-text">
              <strong>{item.title}</strong>
              <p>
                {item.message}
                {item.differences > 0 ? ` Отличий: ${item.differences}.` : ""}
              </p>
            </div>
            <span className="fixture-batch-status">
              {batchLabels[item.status]}
            </span>
            {item.case_id ? (
              <button
                className="icon-button"
                aria-label={`Открыть пример: ${item.title}`}
                onClick={() => onOpen(item.case_id!)}
              >
                <ChevronRight size={18} />
              </button>
            ) : (
              <span className="fixture-batch-no-link" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
