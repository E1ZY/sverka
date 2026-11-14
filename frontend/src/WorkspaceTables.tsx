import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  CopyPlus,
  FileText,
  Loader2,
  Search,
  Trash2,
} from "lucide-react";
import { authFetch } from "./auth";
import { CaseId } from "./CaseId";
import { useDialog } from "./useDialog";
import { formatDuration } from "./duration";

type Check = {
  id: string;
  title: string;
  status: string;
  status_changed_at?: string | null;
  duration_seconds?: number | null;
  user?: string;
  check_type?: string;
  context: { contract: string; stage: number };
};
const statuses: Record<string, string> = {
  draft: "Черновик",
  queued: "В очереди",
  running: "Выполняется",
  completed: "Завершена",
  failed: "Ошибка",
};
const active = (item: Check) => ["queued", "running"].includes(item.status);

export function ChecksTable({
  items,
  query,
  onQuery,
  onOpen,
  onCopy,
  onDelete,
  onClear,
  busy,
}: {
  items: Check[];
  query: string;
  onQuery: (value: string) => void;
  onOpen: (id: string) => void;
  onCopy: (id: string) => void;
  onDelete: (id: string) => void;
  onClear: () => void;
  busy: boolean;
}) {
  const [status, setStatus] = useState("all");
  const visible = items.filter(
    (item) =>
      (status === "all" || item.status === status) &&
      `${item.id} ${item.title} ${item.context.contract} ${item.user || "Общий доступ"}`
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );
  return (
    <section className="panel workspace-register">
      <div className="register-toolbar">
        <h2>
          Сверки <span className="subtle">{items.length}</span>
        </h2>
        <label className="search">
          <Search size={17} />
          <input
            aria-label="Поиск сверок"
            placeholder="ID, название или договор"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
          />
        </label>
        <select
          aria-label="Статус сверки"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="all">Все статусы</option>
          {Object.entries(statuses).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <button
          className="button"
          disabled={busy || !items.some((item) => !active(item))}
          onClick={onClear}
        >
          <Trash2 size={15} />
          Очистить
        </button>
      </div>
      <div className="register-scroll">
        <table className="register-table">
          <thead>
            <tr>
              <th>Идентификатор и название</th>
              <th>Тип проверки</th>
              <th>Изменение статуса</th>
              <th>Статус</th>
              <th>Время проверки</th>
              <th>Пользователь</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id}>
                <td>
                  <button
                    className="register-title"
                    onClick={() => onOpen(item.id)}
                    title={item.status === 'completed' ? 'Открыть сохранённый отчёт' : 'Открыть сверку'}
                  >
                    <strong>{item.title}</strong>
                    <CaseId id={item.id} compact />
                  </button>
                  <small>
                    Договор {item.context.contract} · Этап {item.context.stage}
                  </small>
                </td>
                <td>
                  {item.check_type || "Сверка затрат по первичным документам"}
                </td>
                <td>
                  {item.status_changed_at ? (
                    new Date(item.status_changed_at).toLocaleString("ru-RU")
                  ) : (
                    <span title="Для старых сверок момент изменения статуса не сохранялся">
                      —
                    </span>
                  )}
                </td>
                <td>
                  <span className={"case-status " + item.status}>
                    {statuses[item.status] || item.status}
                  </span>
                </td>
                <td className="duration-cell" title={item.duration_seconds == null
                  ? "Время ещё не записано. Для старых запусков измерение не выполнялось."
                  : "Время обработки без ожидания в очереди"}>
                  {formatDuration(item.duration_seconds)}
                </td>
                <td title="Все проверки доступны в общем рабочем пространстве">
                  {item.user || "Общий доступ"}
                </td>
                <td>
                  <div className="register-actions">
                    <button
                      className="text-button"
                      title="Создать новый отчёт на основе этих документов и параметров"
                      aria-label={`Новый отчёт на основе «${item.title}»`}
                      disabled={busy || active(item)}
                      onClick={() => onCopy(item.id)}
                    >
                      <CopyPlus size={16} /> Новый отчёт
                    </button>
                    {item.status === "completed" && (
                      <a
                        className="icon-button"
                        title="Скачать документы и отчёт по сверке в ZIP"
                        aria-label={`Скачать пакет «${item.title}»`}
                        href={`/api/cases/${item.id}/package.zip`}
                      >
                        <ArrowDownToLine size={17} />
                      </a>
                    )}
                    <button
                      className="icon-button danger-text"
                      title="Удалить сверку"
                      aria-label={`Удалить сверку «${item.title}»`}
                      disabled={busy || active(item)}
                      onClick={() => onDelete(item.id)}
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!visible.length && (
        <div className="empty-small">
          {items.length
            ? "Сверки не найдены. Измените поиск или фильтр."
            : "Пока нет сверок. Создайте новую или откройте учебный пример."}
        </div>
      )}
    </section>
  );
}

type Asset = {
  id: string;
  name: string;
  size: number | null;
  cases: { id: string; title: string }[];
  user: string;
};

function ConfirmOrphanDeletion({
  count,
  onClose,
  onConfirm,
}: {
  count: number;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const dialog = useDialog(onClose, busy);
  return (
    <div className="overlay">
      <section
        className="modal"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label="Удалить документы без сверок"
      >
        <h2>Удалить документы без сверок?</h2>
        <p>
          Будут удалены сохранённые копии документов: {count}. Связанных сверок
          у них нет. Восстановить копии не получится.
        </p>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="register-actions">
          <button
            className="button"
            autoFocus
            disabled={busy}
            onClick={onClose}
          >
            Отмена
          </button>
          <button
            className="button danger"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
              } catch (reason) {
                setError((reason as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Удаляем…" : "Удалить документы"}
          </button>
        </div>
      </section>
    </div>
  );
}

export function DocumentsRegister({
  onOpen,
}: {
  onOpen: (id: string) => void;
}) {
  const [items, setItems] = useState<Asset[]>([]),
    [query, setQuery] = useState(""),
    [applied, setApplied] = useState("");
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [confirm, setConfirm] = useState(false);
  const reload = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await authFetch("/api/documents");
      if (!response.ok) throw new Error("Не удалось загрузить документы.");
      setItems(await response.json());
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void reload();
  }, []);
  const unused = items.filter((item) => !item.cases.length).length;
  const visible = items.filter((item) =>
    `${item.name} ${item.id} ${item.cases.map((check) => `${check.id} ${check.title}`).join(" ")}`
      .toLowerCase()
      .includes(applied.toLowerCase()),
  );
  return (
    <section className="panel workspace-register">
      <form
        className="register-toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          setApplied(query.trim());
        }}
      >
        <h2>
          Документы <span className="subtle">{items.length}</span>
        </h2>
        <label className="search">
          <Search size={17} />
          <input
            aria-label="Поиск документов"
            placeholder="Документ или связанная сверка"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button className="button" type="submit">
          Найти
        </button>
        <button
          className="button"
          type="button"
          disabled={!unused || loading}
          onClick={() => setConfirm(true)}
        >
          <Trash2 size={15} />
          Удалить без сверок ({unused})
        </button>
      </form>
      {error && (
        <p role="alert" className="form-error">
          {error}
          <button className="text-button" onClick={() => void reload()}>
            Повторить
          </button>
        </p>
      )}
      {loading ? (
        <div className="empty-small">
          <Loader2 className="spin" />
          Загружаем документы…
        </div>
      ) : (
        <>
          <div className="register-scroll">
            <table className="register-table">
              <thead>
                <tr>
                  <th>Документ</th>
                  <th>Сверки, в которых он присутствует</th>
                  <th>Пользователь</th>
                  <th>Размер</th>
                  <th>Оригинал</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <span className="document-name">
                        <FileText size={18} />
                        {item.name}
                      </span>
                      <small title={item.id}>
                        SHA-256: {item.id.slice(0, 12)}
                      </small>
                    </td>
                    <td>
                      {item.cases.length ? (
                        <div className="document-links">
                          {item.cases.map((check) => (
                            <button
                              className="text-button"
                              key={check.id}
                              onClick={() => onOpen(check.id)}
                            >
                              {check.title} · {check.id.slice(0, 8)}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <span className="subtle">Без связанных сверок</span>
                      )}
                    </td>
                    <td>{item.user}</td>
                    <td>
                      {item.size == null
                        ? "Недоступен"
                        : `${Math.max(1, Math.round(item.size / 1024))} КБ`}
                    </td>
                    <td>
                      <a
                        className="icon-button"
                        aria-label={`Скачать ${item.name}`}
                        href={`/api/documents/${item.id}/original`}
                      >
                        <ArrowDownToLine size={17} />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!visible.length && (
            <div className="empty-small">
              {items.length
                ? "Документы не найдены. Измените запрос и нажмите «Найти»."
                : "Документы появятся после загрузки в сверку."}
            </div>
          )}
        </>
      )}
      {confirm && (
        <ConfirmOrphanDeletion
          count={unused}
          onClose={() => setConfirm(false)}
          onConfirm={async () => {
            const response = await authFetch("/api/documents/unlinked", {
              method: "DELETE",
            });
            if (!response.ok)
              throw new Error(
                "Не удалось удалить документы. Обновите список и повторите попытку.",
              );
            setConfirm(false);
            await reload();
          }}
        />
      )}
    </section>
  );
}
