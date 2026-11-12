import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { ArrowLeft, ArrowRight, Check, X } from "lucide-react";
import "./tutorial.css";

export type TutorialStep = {
  target: string;
  title: string;
  text: string;
  complete?: boolean;
  waitingText?: string;
  successText?: string;
  content?: ReactNode;
  focusPadding?: number;
  anchor?: string;
};

const overviewSteps: TutorialStep[] = [
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
type Position = { focus: Bounds; left: number; top: number; width?: number; maxHeight?: number };
const focusable = 'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]';

export function CheckTutorial({ root, onClose, steps = overviewSteps, step: controlledStep, onStepChange, onFinish,
  label = "Как сделать проверку", exitLabel = "Пропустить",
  stepOffset = 0, totalSteps = steps.length, finishLabel = "Завершить обучение",
}: {
  root: RefObject<HTMLElement | null>;
  onClose: () => void;
  steps?: TutorialStep[];
  step?: number;
  onStepChange?: (step: number) => void;
  onFinish?: () => void;
  label?: string;
  exitLabel?: string;
  stepOffset?: number;
  totalSteps?: number;
  finishLabel?: string;
}) {
  const [internalStep, setInternalStep] = useState(0);
  const step = controlledStep ?? internalStep;
  const setStep = (value: number) => {
    if (onStepChange) onStepChange(value);
    else setInternalStep(value);
  };
  const [position, setPosition] = useState<Position | null>(null);
  const card = useRef<HTMLElement>(null);
  const options = useRef({ step, steps, onClose });
  options.current = { step, steps, onClose };
  const current = steps[step];
  const canContinue = current.complete !== false;
  const ready = position !== null;

  useEffect(() => {
    if (ready) card.current?.focus({ preventScroll: true });
  }, [step, ready, current.target]);

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        options.current.onClose();
      }
      if (event.key !== "Tab") return;
      const target = root.current?.querySelector<HTMLElement>(`[data-tutorial="${options.current.steps[options.current.step].target}"]`);
      const controls = [
        ...Array.from(card.current?.querySelectorAll<HTMLElement>(focusable) || []),
        ...(target?.matches(focusable) ? [target] : []),
        ...Array.from(target?.querySelectorAll<HTMLElement>(focusable) || []),
      ].filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0 && !element.closest('[aria-hidden="true"]'));
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
    const owner = root.current || card.current?.closest(".new-case-modal, .shell");
    const target = owner?.querySelector<HTMLElement>(`[data-tutorial="${current.target}"]`);
    if (!target) return;
    const anchor = current.anchor ? owner?.querySelector<HTMLElement>(`[data-tutorial="${current.anchor}"]`) : null;
    const scrollTarget = anchor || target;
    scrollTarget.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
    let frame = 0;
    const measure = () => {
      const width = window.innerWidth, height = window.innerHeight;
      const bounds = (element = target, padding = current.focusPadding ?? 7) => {
        const rect = element.getBoundingClientRect();
        const box = {
          left: Math.max(4, rect.left - padding), right: Math.min(width - 4, rect.right + padding),
          top: Math.max(4, rect.top - padding), bottom: Math.min(height - 4, rect.bottom + padding),
        };
        // The evidence can sit inside a scrolling scan, not only the upload form.
        for (let parent = element.parentElement; parent; parent = parent.parentElement) {
          const style = getComputedStyle(parent);
          if (!/(auto|scroll|hidden|clip)/.test(style.overflowX + style.overflowY)) continue;
          const clip = parent.getBoundingClientRect();
          box.left = Math.max(box.left, clip.left);
          box.right = Math.min(box.right, clip.right);
          box.top = Math.max(box.top, clip.top);
          box.bottom = Math.min(box.bottom, clip.bottom);
        }
        box.right = Math.max(box.left, box.right);
        box.bottom = Math.max(box.top, box.bottom);
        return box;
      };
      let focus = bounds();
      const cardWidth = card.current?.offsetWidth || Math.min(360, width - 24);
      const cardHeight = card.current?.offsetHeight || 250;
      if (anchor) {
        const point = bounds(anchor, 16);
        const rightSpace = width - 12 - focus.right - 16;
        const leftSpace = focus.left - 28;
        // Keep the scan and zoom controls uncovered, using the space beside the viewer.
        if (Math.max(rightSpace, leftSpace) >= 260) {
          const right = rightSpace >= leftSpace;
          const panelWidth = Math.min(360, right ? rightSpace : leftSpace);
          setPosition({ focus, width: panelWidth, maxHeight: height - 24,
            left: right ? focus.right + 16 : focus.left - panelWidth - 16,
            top: Math.max(12, Math.min((point.top + point.bottom - cardHeight) / 2, height - cardHeight - 12)) });
          return;
        }
        // On a narrow screen, put a scrollable hint below the enlarged amount.
        const below = height - point.bottom - 28;
        const above = point.top - 28;
        const useBelow = below >= 220 || below >= above;
        const available = Math.max(120, useBelow ? below : above);
        setPosition({ focus, width: Math.min(360, width - 24), maxHeight: available,
          left: Math.max(12, Math.min(point.left, width - Math.min(360, width - 24) - 12)),
          top: useBelow ? point.bottom + 16 : Math.max(12, point.top - 16 - Math.min(cardHeight, available)) });
        return;
      }
      if (focus.bottom + 16 + cardHeight > height - 12 && focus.top - cardHeight - 16 < 12) {
        target.scrollIntoView({ block: "start", inline: "nearest", behavior: "instant" });
        focus = bounds();
      }
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
    const loaded = () => {
      scrollTarget.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
      schedule();
    };
    measure();
    const observer = new ResizeObserver(schedule);
    observer.observe(target);
    if (anchor) observer.observe(anchor);
    if (card.current) observer.observe(card.current);
    window.addEventListener("resize", schedule);
    document.addEventListener("scroll", schedule, true);
    owner?.addEventListener("load", loaded, true);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", schedule);
      document.removeEventListener("scroll", schedule, true);
      owner?.removeEventListener("load", loaded, true);
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
      <section className={"tutorial-card " + (current.anchor ? "tutorial-source-card" : "")} ref={card} tabIndex={-1} role="region"
        aria-label={label} aria-describedby="tutorial-description"
        style={{ left: position?.left ?? 12, top: position?.top ?? 12, width: position?.width,
          maxHeight: position?.maxHeight, visibility: position ? "visible" : "hidden" }}>
        <div className="tutorial-caption">
          <span>{label.toUpperCase()} · {step + stepOffset + 1} ИЗ {totalSteps}</span>
          <button type="button" onClick={onClose} aria-label="Закрыть обучение"><X size={18} /></button>
        </div>
        <div className="tutorial-progress" aria-hidden="true">
          {Array.from({ length: totalSteps }, (_, index) => <span key={index} className={index <= step + stepOffset ? "done" : ""} />)}
        </div>
        <div aria-live="polite" aria-atomic="true">
          <h3>{current.title}</h3>
          <p id="tutorial-description">{current.text}</p>
          {current.content}
          {current.complete !== undefined && <p className={"tutorial-step-status " + (canContinue ? "complete" : "")} role="status">
            {canContinue ? current.successText || "Задание выполнено. Можно продолжать." : current.waitingText || "Выполните задание, чтобы продолжить."}
          </p>}
        </div>
        <div className="tutorial-actions">
          {step > 0
            ? <button type="button" className="text-button" onClick={() => setStep(step - 1)}><ArrowLeft size={16} />Назад</button>
            : <button type="button" className="text-button" onClick={onClose}>{exitLabel}</button>}
          <button type="button" className="button primary" disabled={!canContinue} onClick={() => {
            if (!canContinue) return;
            if (step === steps.length - 1) (onFinish || onClose)();
            else setStep(step + 1);
          }}>
            {step === steps.length - 1 ? <>{finishLabel}<Check size={16} /></> : <>Далее<ArrowRight size={16} /></>}
          </button>
        </div>
      </section>
    </div>
  );
}
