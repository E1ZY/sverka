import { useEffect, useState, type ReactNode } from "react";
import { Check, ChevronDown, ChevronRight, CircleHelp, Loader2, X } from "lucide-react";
import { useDialog } from "./useDialog";
import "./tutorial.css";

export type LessonProgress = {
  caseId: string; runId: string; metric: string | null;
  report: boolean; source: boolean; answered: boolean; hidden: boolean;
};
export type LessonAnswer = "report" | "sources" | "equal";
export type Help = { target: string; title: string; text: string };
const storageKey = "sverka-practice-v1";

function readProgress(): LessonProgress | null {
  try {
    const p = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (!p || typeof p.caseId !== "string" || typeof p.runId !== "string" ||
      !(p.metric === null || typeof p.metric === "string") ||
      ![p.report, p.source, p.answered, p.hidden].every((v) => typeof v === "boolean")) return null;
    return p;
  } catch { return null; }
}

export function usePracticeLesson() {
  const [progress, setProgress] = useState<LessonProgress | null>(readProgress);
  const [feedback, setFeedback] = useState("");
  useEffect(() => {
    try {
      if (progress) localStorage.setItem(storageKey, JSON.stringify(progress));
      else localStorage.removeItem(storageKey);
    } catch { /* The lesson also works when browser storage is unavailable. */ }
  }, [progress]);
  const begin = (caseId: string, runId: string) => {
    setFeedback("");
    setProgress({ caseId, runId, metric: null, report: false, source: false, answered: false, hidden: false });
  };
  const openMetric = (code: string) => setProgress((p) => p && !p.hidden
    ? p.metric === code ? p : { ...p, metric: code, report: false, source: false, answered: false } : p);
  const openSource = (kind: "report" | "source", metric: string) => setProgress((p) =>
    p && !p.hidden && p.metric === metric ? { ...p, [kind]: true } : p);
  const answer = (choice: LessonAnswer, delta: string | null) => {
    if (!progress?.metric || !progress.report || !progress.source || delta === null || !Number.isFinite(Number(delta))) return;
    const correct = Number(delta) > 0 ? "report" : Number(delta) < 0 ? "sources" : "equal";
    if (choice === correct) {
      setFeedback("Верно. Разница — это сумма в отчёте минус сумма по подтверждающим документам.");
      setProgress((p) => p ? { ...p, answered: true } : p);
    } else {
      setFeedback("Пока не совпало. Сравните две суммы: положительная разница означает, что в отчёте больше, отрицательная — что больше по документам.");
    }
  };
  return { progress, feedback, begin, openMetric, openSource, answer,
    hide: () => setProgress((p) => p ? { ...p, hidden: true } : p),
    resume: () => setProgress((p) => p ? { ...p, hidden: false } : p),
    resetRun: (caseId: string, runId: string) => {
      setFeedback("");
      setProgress((p) => p?.caseId === caseId && p.runId !== runId
        ? { ...p, runId, metric: null, report: false, source: false, answered: false } : p);
    },
  };
}

export function PracticeIntro({ onClose, onStart, onOwn, onResume, busy, error }: {
  onClose: () => void; onStart: () => void; onOwn: () => void;
  onResume?: () => void; busy: boolean; error: string;
}) {
  const dialog = useDialog(onClose, busy);
  return <div className="overlay"><section className="modal practice-intro" ref={dialog}
    role="dialog" aria-modal="true" aria-label="Обучение проверке">
    <button className="close" onClick={onClose} disabled={busy} aria-label="Закрыть обучение"><X /></button>
    <span className="eyebrow">ПРАКТИКА НА ГОТОВОМ КОМПЛЕКТЕ</span>
    <h2>Найдите расхождение и проверьте источники</h2>
    <p>КФЗ и первичные документы уже подготовлены. Запустите сверку, найдите проблемную статью и объясните разницу. Задачи отмечаются по вашим действиям.</p>
    <p className="practice-note">Можно исследовать результат самостоятельно. Подсветка включается только по кнопке «Показать где».</p>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <div className="practice-intro-actions">
      {onResume && <button className="button primary" onClick={onResume} disabled={busy}>Продолжить обучение</button>}
      <button className={"button " + (onResume ? "" : "primary")} onClick={onStart} disabled={busy}>
        {busy ? <Loader2 size={17} className="spin" /> : <CircleHelp size={17} />}
        {busy ? "Подготавливаем комплект…" : onResume ? "Начать новую практику" : "Начать на готовом комплекте"}
      </button>
      <button className="text-button" onClick={onOwn} disabled={busy}>Помочь с моими документами</button>
    </div>
  </section></div>;
}

export function LessonQuestion({ actual, expected, answered, feedback, onAnswer }: {
  actual: string | null; expected: string | null; answered: boolean; feedback: string;
  onAnswer: (answer: LessonAnswer) => void;
}) {
  if (actual === null || expected === null) return null;
  const money = (value: string) => Number(value).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return <div className="lesson-question" data-tutorial="lesson-question" aria-label="Сравнение сумм">
    <strong>Что показывает найденное расхождение?</strong>
    <dl><div><dt>В отчёте</dt><dd>{money(actual)} ₽</dd></div><div><dt>По документам</dt><dd>{money(expected)} ₽</dd></div></dl>
    {!answered && <div className="lesson-answers">{([
      ["report", "В отчёте больше"], ["sources", "По документам больше"], ["equal", "Суммы совпадают"],
    ] as const).map(([value, label]) => <button key={value} type="button" className="button" onClick={() => onAnswer(value)}>{label}</button>)}</div>}
    {(feedback || answered) && <p role="status">{feedback || "Ответ верный. Вы сравнили отчёт с подтверждающими документами."}</p>}
  </div>;
}

export function PracticePanel({ progress, ready, failed, onWhere, onHide, onRetry, onOwn, children }: {
  progress: LessonProgress; ready: boolean; failed: boolean;
  onWhere: (target: "metrics" | "report" | "sources") => void;
  onHide: () => void; onRetry: () => void; onOwn: () => void; children?: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const tasks = [
    { title: "Запустить учебную сверку", done: true },
    { title: "Найти статью с расхождением", done: !!progress.metric, target: "metrics" as const },
    { title: "Открыть значение в КФЗ", done: progress.report, target: "report" as const },
    { title: "Открыть подтверждающий документ", done: progress.source, target: "sources" as const },
    { title: "Объяснить разницу сумм", done: progress.answered },
  ];
  const count = tasks.filter((task) => task.done).length;
  return <section className="practice-panel" aria-label="Задачи обучения" tabIndex={-1}>
    <div className="practice-panel-heading">
      <div><span className="eyebrow">УЧЕБНЫЙ КОМПЛЕКТ</span><h2>{count === 5 ? "Вы проверили расхождение по источникам" : "Найдите расхождение и проверьте его"}</h2></div>
      <span className="lesson-count" role="status">{count} из 5</span>
      <button className="icon-button" onClick={onHide} aria-label="Скрыть обучение"><X size={18} /></button>
    </div>
    <progress max={5} value={count} aria-label="Прогресс обучения" />
    <button className="text-button lesson-collapse" aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}>
      {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}{collapsed ? "Показать задачи" : "Свернуть задачи"}
    </button>
    {!collapsed && <>
      <ol className="lesson-tasks">{tasks.map((task, index) => <li key={task.title} className={task.done ? "done" : ""}>
        <span className="lesson-task-number">{task.done ? <Check size={15} /> : index + 1}</span>
        <span>{task.title}{task.done && <small>Выполнено</small>}</span>
        {task.target && <button className="text-button" disabled={!ready || (task.target !== "metrics" && !progress.metric)} onClick={() => onWhere(task.target!)}
          aria-label={`Показать где: ${task.title}`}>Показать где</button>}
      </li>)}</ol>
      {!ready && !failed && <p className="practice-note" role="status">Комплект обрабатывается. Задачи по результатам станут доступны после завершения.</p>}
      {failed && <div role="alert" className="practice-note">Обработка прервана. Прогресс сохранён. <button className="text-button" onClick={onRetry}>Повторить обработку</button></div>}
      {ready && !progress.metric && <p className="practice-note">Начните с таблицы показателей: откройте статью со статусом «Расхождение». Общий итог объединяет несколько статей.</p>}
      {children}
      {count === 5 && <button className="button primary" onClick={onOwn}>Проверить свои документы</button>}
    </>}
    <p className="practice-footnote">Здесь можно пробовать и возвращаться к задачам. Прогресс сохраняется в этом браузере.</p>
  </section>;
}

export function FormTasks({ tasks, onWhere, onClose }: {
  tasks: { target: string; title: string; done: boolean }[];
  onWhere: (help: Help) => void; onClose: () => void;
}) {
  const explanations: Record<string, string> = {
    report: "Добавьте один КФЗ: PDF, PNG или JPEG. По нему определяются суммы отчёта и предлагаются параметры сверки.",
    scope: "Укажите договор, этап и даты внутри одного года. Они определяют, какие расходы и какую строку КФЗ мы проверяем. Проверьте автоматически найденные значения.",
    primary: "Добавьте акты, ведомости и другие документы за выбранный период. По ним рассчитывается подтверждённая сумма расходов.",
  };
  return <section className="form-tasks" aria-label="Подготовка проверки">
    <div className="practice-panel-heading"><strong>Подготовка проверки</strong><span role="status">{tasks.filter((t) => t.done).length} из {tasks.length}</span>
      <button type="button" className="icon-button" onClick={onClose} aria-label="Скрыть задачи"><X size={16} /></button></div>
    <ol className="lesson-tasks">{tasks.map((task, i) => <li key={task.target} className={task.done ? "done" : ""}>
      <span className="lesson-task-number">{task.done ? <Check size={14} /> : i+1}</span><span>{task.title}{task.done && <small>Заполнено — проверьте правильность</small>}</span>
      <button className="text-button" type="button" onClick={() => onWhere({ target: task.target, title: task.title, text: explanations[task.target] })}>Показать где</button>
    </li>)}</ol>
  </section>;
}
