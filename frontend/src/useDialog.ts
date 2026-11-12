import { useEffect, useRef } from "react";

let openDialogs = 0;
let previousOverflow = "";

/** Keep keyboard focus in the topmost dialog and restore it on close. */
export function useDialog(
  onClose: () => void,
  blocked = false,
  enabled = true,
) {
  const ref = useRef<HTMLElement>(null);
  const options = useRef({ onClose, blocked });
  options.current = { onClose, blocked };
  useEffect(() => {
    if (!enabled || !ref.current) return;
    const root = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    if (openDialogs++ === 0) {
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    const focusable = () =>
      Array.from(
        root.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
        ),
      ).filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0 && !element.closest('[aria-hidden="true"]'));
    if (!root.contains(document.activeElement)) focusable()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      const dialogs = document.querySelectorAll(
        '[role="dialog"][aria-modal="true"]',
      );
      if (dialogs[dialogs.length - 1] !== root) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!options.current.blocked) options.current.onClose();
      }
      if (event.key === "Tab") {
        const elements = focusable();
        const first = elements[0],
          last = elements[elements.length - 1];
        if (
          event.shiftKey &&
          (document.activeElement === first ||
            !root.contains(document.activeElement))
        ) {
          event.preventDefault();
          last?.focus();
        } else if (
          !event.shiftKey &&
          (document.activeElement === last ||
            !root.contains(document.activeElement))
        ) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      if (--openDialogs === 0) document.body.style.overflow = previousOverflow;
      if (previous?.isConnected) previous.focus();
    };
  }, [enabled]);
  return ref;
}
