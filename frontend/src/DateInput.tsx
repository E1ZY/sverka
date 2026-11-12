import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { CalendarDays } from "lucide-react";

function displayDate(value: string) {
  return value ? value.split("-").reverse().join(".") : "";
}

function dateDigits(value: string) {
  return value.replace(/\D/g, "");
}

function maskDate(digits: string) {
  return digits.slice(0, 2) + (digits.length >= 2 ? "." + digits.slice(2, 4) : "") +
    (digits.length >= 4 ? "." + digits.slice(4) : "");
}

function isoDate(value: string) {
  const match = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value);
  if (!match) return "";
  const [, day, month, year] = match;
  const d = Number(day), m = Number(month), y = Number(year);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return y > 0 && m >= 1 && m <= 12 && d >= 1 && d <= days[m - 1]
    ? `${year}-${month}-${day}` : "";
}

/** Show a fixed day/month/year order while keeping ISO dates in form data. */
export function DateInput({ name, label, value, onChange, min, required = false }: {
  name: string; label: string; value: string; onChange: (value: string) => void;
  min?: string; required?: boolean;
}) {
  const [text, setText] = useState(() => displayDate(value));
  const emitted = useRef(value);
  const input = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const pendingCaret = useRef<number | null>(null);
  useLayoutEffect(() => {
    if (pendingCaret.current !== null && input.current === document.activeElement) {
      input.current?.setSelectionRange(pendingCaret.current, pendingCaret.current);
    }
    pendingCaret.current = null;
  });
  useEffect(() => {
    // Preserve unfinished manual input when its ISO value is still empty.
    if (value !== emitted.current) {
      emitted.current = value;
      setText(displayDate(value));
    }
  }, [value]);
  useEffect(() => {
    const parsed = isoDate(text);
    input.current?.setCustomValidity(text && !parsed ? "Введите существующую дату в формате ДД.ММ.ГГГГ."
      : parsed && min && parsed < min ? `Укажите дату не раньше ${displayDate(min)}.` : "");
  }, [text, min]);
  const change = (nextText: string, nextValue: string) => {
    setText(nextText);
    emitted.current = nextValue;
    onChange(nextValue);
  };
  const typeDate = (event: React.ChangeEvent<HTMLInputElement>) => {
    const raw = event.currentTarget.value;
    let digits = dateDigits(raw);
    let beforeCaret = dateDigits(raw.slice(0, event.currentTarget.selectionStart ?? raw.length)).length;
    const inputType = (event.nativeEvent as InputEvent).inputType;
    // Backspace/Delete across a fixed dot should delete a digit, not get stuck.
    if (raw !== text && digits === dateDigits(text) &&
        (inputType === "deleteContentBackward" || inputType === "deleteContentForward")) {
      const backward = inputType === "deleteContentBackward";
      const index = beforeCaret - (backward ? 1 : 0);
      if (index >= 0 && index < digits.length) {
        digits = digits.slice(0, index) + digits.slice(index + 1);
        if (backward) beforeCaret--;
      }
    }
    const nextText = maskDate(digits.slice(0, 8));
    pendingCaret.current = Math.min(nextText.length, beforeCaret + (beforeCaret >= 2 ? 1 : 0) + (beforeCaret >= 4 ? 1 : 0));
    change(nextText, isoDate(nextText));
  };
  return <span className="date-input">
    <input ref={input} type="text" aria-label={label} placeholder="ДД.ММ.ГГГГ"
      required={required} inputMode="numeric" autoComplete="off" value={text}
      onChange={typeDate} />
    <button type="button" className="date-picker-button" aria-label={`Выбрать дату: ${label}`}
      onClick={() => picker.current?.showPicker?.()}><CalendarDays size={17} /></button>
    <input ref={picker} className="date-picker-native" type="date" name={name}
      value={value} min={min} tabIndex={-1} aria-hidden="true"
      onChange={(event) => change(displayDate(event.target.value), event.target.value)} />
  </span>;
}
