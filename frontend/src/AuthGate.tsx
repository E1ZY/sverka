import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ArrowRight, Eye, EyeOff, Layers3, Loader2, LockKeyhole } from "lucide-react";
import { AUTH_REQUIRED, authFetch, setCsrfToken } from "./auth";
import "./auth.css";

type Session = { configured: boolean; authenticated: boolean; csrf_token: string | null };

export function AuthGate({ children }: { children: (logout: () => Promise<void>) => ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function readSession(signal?: AbortSignal): Promise<Session> {
    const response = await authFetch("/api/auth/session", { signal });
    if (!response.ok) throw new Error("Не удалось проверить вход. Повторите попытку.");
    return response.json();
  }

  function applySession(value: Session) {
    setCsrfToken(value.csrf_token);
    setSession(value);
  }

  useEffect(() => {
    const controller = new AbortController();
    readSession(controller.signal).then(applySession).catch((reason) => {
      if (!controller.signal.aborted) setError(reason.message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    const expired = () => {
      setCsrfToken(null);
      setSession({ configured: true, authenticated: false, csrf_token: null });
      setPassword("");
      setError("Сессия завершена. Введите пароль ещё раз.");
    };
    const restored = (event: PageTransitionEvent) => {
      if (event.persisted) window.location.reload();
    };
    window.addEventListener(AUTH_REQUIRED, expired);
    window.addEventListener("pageshow", restored);
    return () => {
      controller.abort();
      window.removeEventListener(AUTH_REQUIRED, expired);
      window.removeEventListener("pageshow", restored);
    };
  }, []);

  async function login(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await authFetch("/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "Не удалось войти. Повторите попытку.");
      }
      // Verify that the browser actually accepted the session cookie before
      // mounting the workspace (Secure cookies require HTTPS).
      const next = await readSession();
      if (!next.authenticated) throw new Error("Не удалось сохранить вход. Откройте сайт по HTTPS или обратитесь к администратору.");
      setPassword("");
      applySession(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось подключиться к приложению.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    const response = await authFetch("/api/auth/logout", { method: "POST" });
    if (!response.ok && response.status !== 401) throw new Error("Не удалось выйти. Повторите попытку.");
    setCsrfToken(null);
    setSession({ configured: true, authenticated: false, csrf_token: null });
    setError("");
    setVisible(false);
  }

  if (session?.authenticated) return children(logout);

  return <div className="auth-page">
    <div className="auth-brand"><Layers3 size={27} aria-hidden="true" /><span>сверка</span></div>
    <section className="auth-card" aria-labelledby="auth-title">
      <div className="auth-icon"><LockKeyhole size={25} aria-hidden="true" /></div>
      <h1 id="auth-title">Вход в рабочее пространство</h1>
      {loading ? <p className="auth-status" role="status"><Loader2 size={18} className="spin" /> Проверяем вход…</p>
        : !session ? <><p role="alert" className="form-error">{error}</p><button className="button full" onClick={() => window.location.reload()}>Повторить попытку</button></>
        : !session.configured ? <p className="auth-description">Доступ к приложению ещё не настроен. Обратитесь к администратору.</p>
        : <>
          <p className="auth-description">Введите пароль доступа, чтобы работать с документами и проверками.</p>
          <form onSubmit={login} className="auth-form">
            <label htmlFor="access-password">Пароль доступа</label>
            <div className="auth-password">
              <input id="access-password" name="password" type={visible ? "text" : "password"}
                autoComplete="current-password" required maxLength={1024} autoFocus
                value={password} onChange={(event) => setPassword(event.target.value)}
                aria-invalid={!!error} aria-describedby={error ? "auth-error" : undefined} disabled={busy} />
              <button type="button" onClick={() => setVisible(!visible)} disabled={busy}
                aria-label={visible ? "Скрыть пароль" : "Показать пароль"} aria-pressed={visible}>
                {visible ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {error && <p id="auth-error" className="form-error" role="alert">{error}</p>}
            <button className="button primary full" disabled={busy}>
              {busy ? <><Loader2 size={17} className="spin" /> Входим…</> : <>Войти <ArrowRight size={17} /></>}
            </button>
          </form>
        </>}
    </section>
    <p className="auth-caption">Сверка отчётности по первичным документам</p>
  </div>;
}
