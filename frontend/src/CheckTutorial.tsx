import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { ArrowLeft, ArrowRight, Check, X } from "lucide-react";
import "./tutorial.css";

const steps = [
  {
    target: "report",
    title: "Загрузите отчёт КФЗ",
    text: "Нажмите на выделенную область и выберите один PDF, PNG или JPEG. После загрузки мы попробуем определить договор, этап и период. Для знакомства с формой можно просто нажать «Далее».",
  },
  {
    target: "scope",
    title: "Проверьте параметры сверки",
    text: "Уточните номер договора, нужный этап и даты расходов внутри одного года. Найденные значения можно исправить. Пустые поля заполните вручную: период всей работы может отличаться от периода выбранной строки КФЗ.",
  },
  {
    target: "primary",
    title: "Добавьте первичные документы",
    text: "Выберите акты, ведомости и другие документы, подтверждающие расходы за выбранный период. Можно добавить сразу несколько файлов PDF, DOCX, XLSX, PNG или JPEG, до 25 МБ каждый.",
  },
  {
    target: "complete",
    title: "Укажите полноту комплекта",
    text: "Поставьте галочку, если загрузили все первичные документы за период. Если комплект неполный, оставьте её пустой — вывод сверки будет ограничен подтверждёнными расходами.",
  },
  {
    target: "submit",
    title: "Запустите проверку",
    text: "Когда документы и параметры готовы, нажмите «Начать сверку». После обработки откроются результаты: суммы, расхождения и ссылки на источники. Кнопка «Завершить обучение» только закроет подсказки.",
  },
];

type Bounds = { left: number; top: number; right: number; bottom: number };
type Position = { focus: Bounds; left: number; top: number };
const focusable = 'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]';

export function CheckTutorial({ root, onClose }: {
  root: RefObject<HTMLElement | null>;
  onClose: () => void;
}) {
  const [step, setStep] = useState(0);
  const [position, setPosition] = useState<Position | null>(null);
  const card = useRef<HTMLElement>(null);
  const options = useRef({ step, onClose });
  options.current = { step, onClose };
  const current = steps[step];
  const ready = position !== null;

  useEffect(() => {
    if (ready) card.current?.focus({ preventScroll: true });
  }, [step, ready]);

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        options.current.onClose();
      }
      if (event.key !== "Tab") return;
      const target = root.current?.querySelector<HTMLElement>(`[data-tutorial="${steps[options.current.step].target}"]`);
      const controls = [
        ...Array.from(card.current?.querySelectorAll<HTMLElement>(focusable) || []),
        ...(target?.matches(focusable) ? [target] : []),
        ...Array.from(target?.querySelectorAll<HTMLElement>(focusable) || []),
      ].filter((element) => element.getClientRects().length > 0);
      if (!controls.length) return;
      const index = controls.indexOf(document.activeElement as HTMLElement);
      const next = index < 0 ? (event.shiftKey ? controls.length - 1 : 0)
        : (index + (event.shiftKey ? -1 : 1) + controls.length) % controls.length;
      event.preventDefault();
      event.stopPropagation();
      controls[next].focus();
    };
    document.addEventListener("keydown", keyboard, true);
    return () => {
      document.removeEventListener("keydown", keyboard, true);
      if (root.current?.isConnected) {
        root.current.querySelector<HTMLElement>("[data-tutorial-start]")?.focus({ preventScroll: true });
      }
    };
  }, [root]);

  useLayoutEffect(() => {
    // Child layout effects run before the parent's ref is attached on first mount.
    const owner = root.current || card.current?.closest(".new-case-modal");
    const target = owner?.querySelector<HTMLElement>(`[data-tutorial="${current.target}"]`);
    if (!target) return;
    target.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
    let frame = 0;
    const measure = () => {
      const rect = target.getBoundingClientRect();
      const scroller = owner?.querySelector(".new-case-fields");
      const clip = scroller?.contains(target) ? scroller.getBoundingClientRect() : null;
      const width = window.innerWidth, height = window.innerHeight;
      const focus = {
        left: Math.max(4, rect.left - 7), right: Math.min(width - 4, rect.right + 7),
        top: Math.max(4, rect.top - 7, clip?.top ?? 0),
        bottom: Math.min(height - 4, rect.bottom + 7, clip?.bottom ?? height),
      };
      focus.bottom = Math.max(focus.top, focus.bottom);
      const cardWidth = card.current?.offsetWidth || Math.min(360, width - 24);
      const cardHeight = card.current?.offsetHeight || 250;
      const below = focus.bottom + 16;
      const above = focus.top - cardHeight - 16;
      const top = below + cardHeight <= height - 12 ? below
        : above >= 12 ? above : Math.max(12, height - cardHeight - 12);
      const left = Math.max(12, Math.min(focus.left, width - cardWidth - 12));
      setPosition({ focus, left, top });
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    measure();
    const observer = new ResizeObserver(schedule);
    observer.observe(target);
    if (card.current) observer.observe(card.current);
    window.addEventListener("resize", schedule);
    document.addEventListener("scroll", schedule, true);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", schedule);
      document.removeEventListener("scroll", schedule, true);
    };
  }, [root, current]);

  const focus = position?.focus;
  return (
    <div className="check-tutorial">
      {position && focus && <>
        <div className="tutorial-shade" style={{ left: 0, top: 0, width: "100%", height: focus.top }} />
        <div className="tutorial-shade" style={{ left: 0, top: focus.bottom, width: "100%", bottom: 0 }} />
        <div className="tutorial-shade" style={{ left: 0, top: focus.top, width: focus.left, height: focus.bottom - focus.top }} />
        <div className="tutorial-shade" style={{ left: focus.right, right: 0, top: focus.top, height: focus.bottom - focus.top }} />
        <div className="tutorial-focus" aria-hidden="true" style={{
          left: focus.left, top: focus.top, width: focus.right - focus.left, height: focus.bottom - focus.top,
        }} />
      </>}
      <section className="tutorial-card" ref={card} tabIndex={-1} role="region"
        aria-label="Как сделать проверку" aria-describedby="tutorial-description"
        style={{ left: position?.left ?? 12, top: position?.top ?? 12, visibility: position ? "visible" : "hidden" }}>
        <div className="tutorial-caption">
          <span>КАК СДЕЛАТЬ ПРОВЕРКУ · {step + 1} ИЗ {steps.length}</span>
          <button type="button" onClick={onClose} aria-label="Закрыть обучение"><X size={18} /></button>
        </div>
        <div className="tutorial-progress" aria-hidden="true">
          {steps.map((item, index) => <span key={item.target} className={index <= step ? "done" : ""} />)}
        </div>
        <div aria-live="polite" aria-atomic="true">
          <h3>{current.title}</h3>
          <p id="tutorial-description">{current.text}</p>
        </div>
        <div className="tutorial-actions">
          {step > 0
            ? <button type="button" className="text-button" onClick={() => setStep(step - 1)}><ArrowLeft size={16} />Назад</button>
            : <button type="button" className="text-button" onClick={onClose}>Пропустить</button>}
          <button type="button" className="button primary" onClick={() => step === steps.length - 1 ? onClose() : setStep(step + 1)}>
            {step === steps.length - 1 ? <>Завершить обучение<Check size={16} /></> : <>Далее<ArrowRight size={16} /></>}
          </button>
        </div>
      </section>
    </div>
  );
}
