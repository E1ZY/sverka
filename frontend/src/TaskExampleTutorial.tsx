import { useState, type CSSProperties } from "react";
import { CheckCheck, Sparkles, X } from "lucide-react";
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
  const [celebration, setCelebration] = useState(0);
  return <div className="overlay example-success-overlay">
    <div key={celebration} className="example-confetti" aria-hidden="true">{Array.from({ length: 72 }, (_, i) => <i key={i} style={{
      left: ((i * 37 + 11) % 100) + "%",
      backgroundColor: ["#4166df", "#eeb14f", "#e4789c", "#4eae90", "#9b7be2"][i % 5],
      "--delay": (i % 12) * 0.07 + "s",
      "--duration": (2.8 + (i % 7) * 0.16) + "s",
      "--drift": ((i * 23) % 180 - 90) + "px",
      "--turn": (i % 2 ? "720deg" : "-720deg"),
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
      <button type="button" className="text-button confetti-replay" onClick={() => setCelebration((value) => value + 1)}>
        <Sparkles size={16} />Ещё конфетти
      </button>
    </section>
  </div>;
}
