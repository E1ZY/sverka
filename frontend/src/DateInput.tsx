import { useEffect, useRef, useState } from "react";
import { CalendarDays } from "lucide-react";

function displayDate(value: string) {
  return value ? value.split("-").reverse().join(".") : "";
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
  return <span className="date-input">
    <input ref={input} type="text" aria-label={label} placeholder="ДД.ММ.ГГГГ"
      required={required} maxLength={10} autoComplete="off" value={text}
      onChange={(event) => change(event.target.value, isoDate(event.target.value))} />
    <button type="button" className="date-picker-button" aria-label={`Выбрать дату: ${label}`}
      onClick={() => picker.current?.showPicker?.()}><CalendarDays size={17} /></button>
    <input ref={picker} className="date-picker-native" type="date" name={name}
      value={value} min={min} tabIndex={-1} aria-hidden="true"
      onChange={(event) => change(displayDate(event.target.value), event.target.value)} />
  </span>;
}
