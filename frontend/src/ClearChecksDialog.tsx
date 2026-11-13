import { useState } from "react";
import { CircleAlert, Loader2, Trash2, X } from "lucide-react";
import { useDialog } from "./useDialog";
import { CaseId } from "./CaseId";

export function ClearChecksDialog({ count, activeCount, caseTitle, caseId, onClose, onConfirm }: {
  count: number;
  activeCount: number;
  caseTitle?: string;
  caseId?: string;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const single = caseTitle !== undefined;
  const dialog = useDialog(onClose, busy);
  const confirm = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await onConfirm();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return <div className="overlay clear-checks-overlay" onClick={(event) => {
    if (!busy && event.target === event.currentTarget) onClose();
  }}>
    <section className="modal clear-checks-dialog" ref={dialog} role="dialog" aria-modal="true"
      aria-labelledby="clear-checks-title" aria-describedby="clear-checks-warning">
      <button type="button" className="close" aria-label="Закрыть предупреждение" disabled={busy} onClick={onClose}><X /></button>
      <span className="clear-checks-icon"><Trash2 size={25} /></span>
      <h2 id="clear-checks-title">{single ? "Удалить проверку?" : "Очистить последние проверки?"}</h2>
      {single && caseId && <div className="delete-check-id"><CaseId id={caseId} /></div>}
      <p id="clear-checks-warning">{single
        ? <>Будет удалена проверка <strong className="delete-check-name">«{caseTitle}»</strong> вместе с загруженными копиями документов, результатами и историей запусков. <strong>Восстановить её не получится.</strong></>
        : <>Будут удалены проверки из списка последних: <strong>{count}</strong>, а также их загруженные копии документов, результаты и история запусков. <strong>Восстановить их не получится.</strong></>}</p>
      <p className="muted">Исходные файлы на вашем компьютере сохранятся.</p>
      {activeCount > 0 && <p className="notice">Выполняющиеся проверки останутся в списке: {activeCount}.</p>}
      {error && <p className="form-error" role="alert"><CircleAlert size={17} />{error}</p>}
      <div className="clear-checks-actions">
        <button type="button" className="button" autoFocus disabled={busy} onClick={onClose}>Отмена</button>
        <button type="button" className="button danger" disabled={busy} onClick={confirm}>
          {busy ? <Loader2 size={17} className="spin" /> : <Trash2 size={17} />}
          {busy ? (single ? "Удаляем проверку…" : "Удаляем проверки…") : (single ? "Удалить проверку" : "Удалить проверки")}
        </button>
      </div>
    </section>
  </div>;
}
