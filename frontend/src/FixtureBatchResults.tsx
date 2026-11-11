import { CheckCheck, ChevronRight, CircleAlert, Loader2 } from "lucide-react";

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
  return (
    <div className="fixture-batch-panel">
      <div className="fixture-batch-overview" role="status" aria-live="polite">
        <div className="fixture-batch-heading">
          <h3>{running ? "Проверяем весь каталог" : "Прогон завершён"}</h3>
          <span>
            {batch.done} из {batch.total} · {batch.progress}%
          </span>
        </div>
        <progress
          aria-label="Прогресс общего прогона"
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
          <span className={batch.counts.failed + batch.counts.errors ? "error" : ""}>
            <strong>{batch.counts.failed + batch.counts.errors}</strong>Новые ошибки
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
            ? "Прогон продолжится, если закрыть окно. Результаты сохраняются автоматически."
            : "Откройте кейс, чтобы посмотреть расчёт, источники и отличия от эталона."}
        </p>
      </div>
      <div className="fixture-batch-list" aria-label="Результаты общего прогона">
        {batch.items.map((item) => (
          <div className={"fixture-batch-row " + item.status} key={item.fixture_id}>
            <span className="fixture-batch-icon">
              {item.status === "running" ? (
                <Loader2 size={19} className="spin" />
              ) : item.status === "passed" || item.status === "unexpected_pass" ? (
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
                aria-label={`Открыть кейс: ${item.title}`}
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
