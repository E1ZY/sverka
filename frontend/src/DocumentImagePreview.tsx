import { useLayoutEffect, useRef, useState } from "react";
import { Focus, Maximize2, ZoomIn, ZoomOut } from "lucide-react";

type ViewMode = "page" | "evidence" | "manual";

export function DocumentImagePreview({ src, alt, bbox, evidenceText = "", amount, focusInitially, onError }: {
  src: string; alt: string; bbox?: number[]; focusInitially: boolean; onError: () => void;
  evidenceText?: string; amount?: string;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const page = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [fitWidth, setFitWidth] = useState(300);
  const [frameHeight, setFrameHeight] = useState(0);
  const [mode, setMode] = useState<ViewMode>(focusInitially ? "evidence" : "page");
  const [manualWidth, setManualWidth] = useState(300);
  const box = bbox?.length === 4 && bbox.every((value) => Number.isFinite(value) && value >= 0 && value <= 1)
    && bbox[2] > bbox[0] && bbox[3] > bbox[1] ? bbox : undefined;
  const boxKey = box?.join(",");
  const aspect = size.width ? size.height / size.width : 1;
  const fitPageWidth = size.width && frameHeight ? Math.min(fitWidth, frameHeight / aspect) : fitWidth;
  const minimumWidth = Math.min(fitPageWidth, fitWidth * 0.5);
  const amounts = Array.from(evidenceText.matchAll(/\d[\d \u00a0]*[.,]\d{2}(?!\d)/g));
  const amountMatch = amount != null ? amounts.find((match) =>
    Number(match[0].replace(/[ \u00a0]/g, "").replace(",", ".")) === Number(amount))
    : amounts.length === 1 ? amounts[0] : undefined;
  // Long OCR lines may contain an amount at their far end. Center that part,
  // while retaining the original highlight as the source evidence.
  const amountCenter = amountMatch && evidenceText.length
    ? (amountMatch.index + amountMatch[0].length / 2) / evidenceText.length : 0.5;
  // A text-height target keeps even a tiny cell legible on a wide financial table.
  const readableWidth = box ? 28 / ((box[3] - box[1]) * aspect) : fitWidth;
  const pageWidth = mode === "evidence" ? Math.max(fitWidth, Math.min(6000, readableWidth))
    : mode === "manual" ? Math.max(minimumWidth, Math.min(6000, manualWidth)) : fitPageWidth;
  useLayoutEffect(() => {
    const element = frame.current;
    if (!element) return;
    const measure = () => {
      const style = getComputedStyle(element);
      setFitWidth(Math.max(100, element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)));
      setFrameHeight(Math.max(100, element.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    const viewport = frame.current, sheet = page.current;
    if (!viewport || !sheet || !size.width) return;
    if (mode === "page") {
      viewport.scrollLeft = 0;
      viewport.scrollTop = 0;
      return;
    }
    const x = box ? box[0] + (box[2] - box[0]) * amountCenter : 0.5;
    const y = box ? (box[1] + box[3]) / 2 : 0.5;
    viewport.scrollLeft = sheet.offsetLeft + x * pageWidth - viewport.clientWidth / 2;
    viewport.scrollTop = sheet.offsetTop + y * pageWidth * aspect - viewport.clientHeight / 2;
  }, [mode, pageWidth, fitWidth, frameHeight, size, boxKey, amountCenter]);
  const zoom = (factor: number) => {
    setManualWidth(pageWidth * factor);
    setMode("manual");
  };
  return <div className="document-image-preview" data-tutorial="example-evidence-view">
    <div className="document-preview-toolbar" role="group" aria-label="Масштаб документа">
      <div className="document-zoom-controls">
        <button type="button" className="icon-button" aria-label="Уменьшить масштаб" disabled={pageWidth <= minimumWidth} onClick={() => zoom(1 / 1.25)}><ZoomOut size={18} /></button>
        <output aria-label="Масштаб">{Math.round(pageWidth / fitWidth * 100)}%</output>
        <button type="button" className="icon-button" aria-label="Увеличить масштаб" disabled={pageWidth >= 6000} onClick={() => zoom(1.25)}><ZoomIn size={18} /></button>
      </div>
      {box && <button type="button" className="text-button" aria-pressed={mode === "evidence"} onClick={() => setMode("evidence")}><Focus size={16} />К фрагменту</button>}
      <button type="button" className="text-button" aria-pressed={mode === "page"} onClick={() => setMode("page")}><Maximize2 size={16} />Вся страница</button>
    </div>
    <div className="document-image-viewport" ref={frame} tabIndex={0} role="region" aria-label="Просмотр страницы документа">
      <div className="page-image" ref={page} style={{ width: pageWidth }}>
        <img alt={alt} src={src} onError={onError}
          onLoad={(event) => setSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
        {box && <span className="evidence-highlight" data-tutorial="example-evidence" style={{
          left: box[0] * 100 + "%", top: box[1] * 100 + "%",
          width: (box[2] - box[0]) * 100 + "%", height: (box[3] - box[1]) * 100 + "%",
        }} />}
      </div>
    </div>
  </div>;
}
