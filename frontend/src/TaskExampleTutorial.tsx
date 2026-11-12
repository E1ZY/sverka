import type { CSSProperties } from "react";
import { CheckCheck, Loader2, Play, X } from "lucide-react";
import { useDialog } from "./useDialog";

export type ExampleAnswer = "report" | "primary" | "equal";
export type TaskExample = {
  step: number;
  caseId: string | null;
  article: string | null;
  reportOpened: boolean;
  primaryDocument: string | null;
  answer: ExampleAnswer | null;
};

export function TaskExampleIntro({ busy, started, error, onStart, onClose }: {
  busy: boolean; started: boolean; error: string; onStart: () => void; onClose: () => void;
}) {
  const dialog = useDialog(onClose, busy);
  return <div className="overlay"><section className="modal task-example-intro" role="dialog"
    aria-modal="true" aria-label="Исходный комплект задания" ref={dialog}>
    <button className="close" onClick={onClose} disabled={busy} aria-label="Закрыть учебный пример"><X /></button>
    <span className="eyebrow">ПРАКТИКА С ПОДСКАЗКАМИ</span>
    <h2>Проверим исходный комплект задания</h2>
    <p>Отчёт КФЗ и 22 первичных документа уже подготовлены. В примере мы проверяем договор <strong>24/03/15-01</strong>, этап <strong>3</strong>, период <strong>01.01.2026–31.05.2026</strong>.</p>
    <p>Найдите расхождение и проверьте его по источникам. Каждый следующий шаг откроется после выполнения текущего задания.</p>
    {error && <p className="error-banner" role="alert">{error}</p>}
    <button className="button primary" data-tutorial="example-launch" disabled={busy || started} onClick={onStart}>
      {busy ? <Loader2 size={18} className="spin" /> : started ? <CheckCheck size={18} /> : <Play size={18} />}
      {busy ? "Подготавливаем комплект…" : started ? "Пример запущен" : "Запустить пример"}
    </button>
  </section></div>;
}

export function ExampleQuestion({ actual, expected, answer, onAnswer }: {
  actual: string | null; expected: string | null; answer: ExampleAnswer | null;
  onAnswer: (answer: ExampleAnswer) => void;
}) {
  const money = (value: string | null) => value === null ? "Не определено" :
    Number(value).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " ₽";
  return <div className="example-question">
    <dl><div><dt>В отчёте</dt><dd>{money(actual)}</dd></div><div><dt>По документам</dt><dd>{money(expected)}</dd></div></dl>
    <div className="example-answers" role="group" aria-label="Что означает расхождение">
      {([
        ["report", "В отчёте больше"], ["primary", "По документам больше"], ["equal", "Суммы совпадают"],
      ] as const).map(([value, text]) => <button type="button" className="button" key={value}
        aria-pressed={answer === value} onClick={() => onAnswer(value)}>{text}</button>)}
    </div>
  </div>;
}

export function TaskExampleSuccess({ article, difference, onClose, onNew }: {
  article: string; difference: string; onClose: () => void; onNew: () => void;
}) {
  const dialog = useDialog(onClose);
  return <div className="overlay example-success-overlay">
    <div className="example-confetti" aria-hidden="true">{Array.from({ length: 72 }, (_, i) => <i key={i} style={{
      left: ((i * 37 + 11) % 100) + "%",
      backgroundColor: ["#4166df", "#eeb14f", "#e4789c", "#4eae90", "#9b7be2"][i % 5],
      animationDelay: (i % 12) * 0.07 + "s",
      animationDuration: (2.8 + (i % 7) * 0.16) + "s",
      "--drift": ((i * 23) % 180 - 90) + "px",
      "--turn": (i % 2 ? "720deg" : "-720deg"),
      "--rest-top": ((i * 41 + 7) % 100) + "%",
      "--rest-turn": ((i * 29) % 360) + "deg",
    } as CSSProperties} />)}</div>
    <section className="modal example-success" role="dialog" aria-modal="true" aria-label="Учебный пример пройден" ref={dialog}>
      <button className="close" onClick={onClose} aria-label="Закрыть поздравление"><X /></button>
      <span className="example-success-icon"><CheckCheck size={32} /></span>
      <h2>Учебный пример пройден!</h2>
      <p>Вы нашли расхождение по статье <strong>{article}</strong> на <strong>{difference} ₽</strong>, открыли КФЗ и подтверждающий документ, затем верно сравнили суммы.</p>
      <p>Теперь можно проверить свой комплект. Результат учебной сверки остаётся в списке проверок.</p>
      <div className="example-success-actions">
        <button className="button" onClick={onClose}>К результатам</button>
        <button className="button primary" onClick={onNew}>Новая проверка</button>
      </div>
    </section>
  </div>;
}
