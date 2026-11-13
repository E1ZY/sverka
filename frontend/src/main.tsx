import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronRight,
  CircleAlert,
  CircleHelp,
  Clock3,
  FileCheck2,
  Files,
  FileText,
  FolderOpen,
  GraduationCap,
  History,
  Layers3,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  SlidersHorizontal,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import "./style.css";
import "./ux.css";
import { FixtureBatchResults, type FixtureBatch } from "./FixtureBatchResults";
import { useDialog } from "./useDialog";
import { useReportContext } from "./useReportContext";
import { DateInput } from "./DateInput";
import { DocumentImagePreview } from "./DocumentImagePreview";
import { ClearChecksDialog } from "./ClearChecksDialog";
import { CheckTutorial, type TutorialStep } from "./CheckTutorial";
import { ExampleQuestion, TaskExampleSuccess, type TaskExample } from "./TaskExampleTutorial";

type Evidence = {
  text: string;
  page?: number;
  bbox?: number[];
  sheet?: string;
  range?: string;
  paragraph?: number;
  table?: number;
  row?: number;
  column?: number;
  confidence?: number;
};
type Fact = {
  article?: string;
  amount?: string;
  contract?: string;
  number?: string;
  period_start?: string;
  period_end?: string;
  amount_evidence?: Evidence;
  classification_evidence?: Evidence;
  fragments?: Evidence[];
  needs_review?: boolean;
};
type Doc = {
  id: string;
  name: string;
  role: string;
  error?: string;
  disposition?: string;
  extraction?: Fact;
};
type Term = {
  document_id: string;
  name: string;
  amount: string;
  evidence?: Evidence;
  classification_evidence?: Evidence;
  calculation?: { amount: string; evidence: Evidence }[];
  reviewed?: boolean;
};
type Metric = {
  code: string;
  name: string;
  status: string;
  actual: string | null;
  expected: string | null;
  delta: string | null;
  confirmed_subtotal?: string;
  reason?: string;
  report_evidence?: Evidence;
  terms: Term[];
};
type Finding = {
  type: string;
  document_id: string;
  name?: string;
  detail: string;
};
type Result = {
  metrics: Metric[];
  unverified: { code: string; name: string; reason: string }[];
  findings: Finding[];
  documents: Doc[];
  summary: { scope: string; included_documents: number };
  pipeline_version: string;
};
type FixtureDifference = {
  label: string;
  kind: "money" | "status" | "count" | "boolean";
  expected: string | number | boolean | null;
  actual: string | number | boolean | null;
};
type FixtureComparison = {
  available: boolean;
  matches: boolean | null;
  fixture_id?: string;
  title?: string;
  known_limitation?: string | null;
  differences: FixtureDifference[];
  message?: string;
};
type Case = {
  id: string;
  title: string;
  status: string;
  created_at?: string;
  context: {
    contract: string;
    stage: number;
    period_start: string;
    period_end: string;
    complete_package: boolean;
    fixture_id?: string;
  };
  active_run_id?: string;
  documents?: Doc[];
  result?: Result;
  fixture_comparison?: FixtureComparison | null;
  runs?: {
    id: string;
    status: string;
    progress: number;
    message: string;
    created_at: string;
  }[];
  reviews?: {
    id: string;
    document_id: string;
    changes: object;
    before: object;
    reason: string;
    created_at: string;
  }[];
};
type Fixture = {
  id: string;
  origin: "task" | "generated";
  title: string;
  description: string;
  context: Case["context"];
  known_limitation: string | null;
  input_files: number;
};
type FixtureLaunch = {
  status: "queued" | "rejected";
  case_id?: string;
  filename?: string;
  matches_expected?: boolean;
  actual_http_status?: number;
  expected_http_status?: number;
};
const articles: Record<string, string> = {
  "0200": "Оплата труда",
  "0300": "Страховые взносы",
  "0800": "Общепроизводственные",
  "0900": "Общехозяйственные",
};
const labels: Record<string, string> = {
  MATCH: "Подтверждено",
  MISMATCH: "Расхождение",
  INSUFFICIENT_DATA: "Недостаточно данных",
  NEEDS_REVIEW: "Требует проверки",
  INCLUDED: "Учтён",
  DUPLICATE: "Дубликат",
  OUT_OF_PERIOD: "Вне периода",
  WRONG_CONTRACT: "Другой договор",
  EXTRACTION_ERROR: "Ошибка чтения",
  MISSING_FIELDS: "Нет реквизитов",
  MISSING_DOCUMENT: "Недостающий документ",
  AMBIGUOUS_LINK: "Неоднозначная статья",
  LOW_CONFIDENCE: "Проверить распознавание",
  PERIOD_OVERLAP: "Пересечение периода",
  CONFLICTING_DOCUMENT: "Конфликт документов",
  REPORT_ARITHMETIC: "Арифметика отчёта",
};
const rub = (value: string | null | undefined) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("ru-RU", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(Number(value));
const dt = (value: string) =>
  new Date(value + "T12:00:00").toLocaleDateString("ru-RU");
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch("/api" + path, init);
  if (!r.ok) {
    let detail = await r.json().catch(() => ({ detail: "Ошибка соединения" }));
    throw Object.assign(
      new Error(
        typeof detail.detail === "string"
          ? detail.detail
          : JSON.stringify(detail.detail),
      ),
      { status: r.status },
    );
  }
  return r.json();
}
const json = (body: unknown) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status.toLowerCase()}>
      {status === "MATCH" || status === "INCLUDED" ? (
        <Check size={13} />
      ) : status === "MISMATCH" ? (
        <CircleAlert size={13} />
      ) : (
        <span className="badge-dot" />
      )}
      {labels[status] || status}
    </span>
  );
}

function App() {
  const [cases, setCases] = useState<Case[]>([]),
    [selected, setSelected] = useState<string | null>(
      localStorage.getItem("active-case"),
    ),
    [current, setCurrent] = useState<Case | null>(null),
    [tab, setTab] = useState("checks"),
    [filter, setFilter] = useState("all"),
    [search, setSearch] = useState(""),
    [caseQuery, setCaseQuery] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [clearChecks, setClearChecks] = useState<{ ids: string[]; activeCount: number; caseTitle?: string } | null>(null),
    [newOpen, setNewOpen] = useState(false),
    [newTutorial, setNewTutorial] = useState(false),
    [example, setExample] = useState<TaskExample | null>(null),
    [exampleSuccess, setExampleSuccess] = useState<{ article: string; difference: string } | null>(null),
    [fixturesOpen, setFixturesOpen] = useState(false),
    [detail, setDetail] = useState<Metric | null>(null),
    [source, setSource] = useState<{ doc: Doc; evidence?: Evidence } | null>(
      null,
    );
  const shell = useRef<HTMLDivElement>(null);
  const removedCaseIds = useRef(new Set<string>());
  const selection = useRef(selected);
  selection.current = selected;
  const detailDialog = useDialog(() => setDetail(null), false, !!detail);
  const openNew = (tutorial = false) => {
    setNewTutorial(tutorial);
    setNewOpen(true);
  };
  const cancelExample = () => {
    setExample(null);
    setDetail(null);
    setSource(null);
  };
  const openExample = () => {
    // Preparation uses the ordinary upload form before the result steps begin.
    setExample({ step: -1, caseId: null, article: null, reportOpened: false, primaryDocument: null, answer: null });
    setExampleSuccess(null);
    setNewOpen(false);
    setFixturesOpen(false);
    setDetail(null);
    setSource(null);
  };
  const refresh = async () => {
    setCases((await api<Case[]>("/cases")).filter((item) => !removedCaseIds.current.has(item.id)));
    if (selected && selection.current === selected) {
      const c = await api<Case>("/cases/" + selected);
      if (selection.current === selected) setCurrent(c);
    }
  };
  useEffect(() => {
    refresh().catch((e) => {
      if (selection.current !== selected) return;
      if (e.status === 404) overview();
      else setError(e.message);
    });
  }, [selected]);
  const running = current?.status === "running" || current?.status === "queued";
  const pendingCases = cases.some((item) => ["queued", "running"].includes(item.status));
  useEffect(() => {
    if (!running && !pendingCases) return;
    const id = setInterval(
      () => refresh().catch((e) => setError(e.message)),
      1000,
    );
    return () => clearInterval(id);
  }, [running, pendingCases, selected]);
  const choose = (id: string) => {
    if (!cases.some((item) => item.id === id)) setCaseQuery("");
    if (selection.current !== id) setCurrent(null);
    else refresh().catch((e) => setError(e.message));
    selection.current = id;
    setSelected(id);
    localStorage.setItem("active-case", id);
    setDetail(null);
    setSource(null);
    setTab("checks");
    setFilter("all");
    setSearch("");
    setError("");
  };
  const overview = () => {
    selection.current = null;
    setSelected(null);
    setCurrent(null);
    localStorage.removeItem("active-case");
    setTab("checks");
    setDetail(null);
    setSource(null);
    setError("");
  };
  const clearableCases = cases.filter((item) => !["queued", "running"].includes(item.status));
  const openClearChecks = () => {
    if (!clearableCases.length) return;
    setClearChecks({ ids: clearableCases.map((item) => item.id), activeCount: cases.length - clearableCases.length });
  };
  const openDeleteCheck = (item: Case) => {
    if (busy || ["queued", "running"].includes(item.status)) return;
    setClearChecks({ ids: [item.id], activeCount: 0, caseTitle: item.title });
  };
  const confirmClearChecks = async () => {
    if (!clearChecks) return;
    const ids = new Set(clearChecks.ids);
    const result = await api<{ deleted_ids: string[]; cleanup_failed: string[] }>("/cases", {
      method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ case_ids: [...ids] }),
    });
    ids.forEach((id) => removedCaseIds.current.add(id));
    setCases((items) => items.filter((item) => !ids.has(item.id)));
    if (clearChecks.caseTitle === undefined) setCaseQuery("");
    if (selection.current && ids.has(selection.current)) overview();
    if (example?.caseId && ids.has(example.caseId)) cancelExample();
    setExampleSuccess(null);
    setClearChecks(null);
    try {
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
    if (result.cleanup_failed.length) setError("Проверки удалены из списка, но не удалось удалить некоторые загруженные копии файлов. Проверьте права доступа к папке данных.");
  };
  const action = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const start = () =>
    action(async () => {
      await api("/cases/" + selected + "/runs", { method: "POST" });
      await refresh();
    });
  const result = current?.result;
  const docs = result?.documents || current?.documents || [];
  const report = docs.find((d) => d.role === "report");
  const exampleCase = !!example?.caseId && example.caseId === current?.id && selected === example.caseId;
  const exampleMetric = exampleCase ? result?.metrics.find((m) => m.status === "MISMATCH" && m.code !== "total") : undefined;
  const exampleReady = !!(exampleMetric?.report_evidence && exampleMetric.terms.length && report && current?.status === "completed");
  const openMetric = (metric: Metric) => {
    setDetail(metric);
    if (exampleCase && example?.step === 2 && metric.code === exampleMetric?.code) {
      setExample((value) => value ? { ...value, article: metric.code } : value);
    }
  };
  const showSource = (id: string, evidence?: Evidence) => {
    const doc = docs.find((d) => d.id === id);
    if (doc) {
      setSource({ doc, evidence });
      if (exampleCase && detail?.code === exampleMetric?.code && evidence) {
        if (example?.step === 3 && doc.role === "report" && evidence === detail?.report_evidence) {
          setExample((value) => value ? { ...value, reportOpened: true } : value);
        }
        if (example?.step === 4 && doc.role === "primary" && detail?.terms.some((term) => term.document_id === id)) {
          setExample((value) => value ? { ...value, primaryDocument: id } : value);
        }
      }
    }
  };
  const numericDelta = exampleMetric?.delta == null ? NaN : Number(exampleMetric.delta);
  const correctAnswer = !Number.isFinite(numericDelta) ? null : numericDelta > 0 ? "report" : numericDelta < 0 ? "primary" : "equal";
  const answerCorrect = !!correctAnswer && example?.answer === correctAnswer;
  const sourceImageEvidence = !!source?.evidence?.bbox && /\.(pdf|png|jpe?g)$/i.test(source.doc.name);
  const exampleSourceValue = source?.doc.role === "report" ? exampleMetric?.actual
    : exampleMetric?.terms.find((term) => term.document_id === source?.doc.id)?.amount;
  const exampleSourceReadout = source && exampleSourceValue != null ? <div className="tutorial-source-readout">
    <span>{source.doc.role === "report" ? "Сумма в КФЗ" : "Сумма в этом документе"}</span>
    <strong>{rub(exampleSourceValue)} ₽</strong>
    <small>Этап {current?.context.stage} · {current?.context.period_start.slice(0, 4)} год · статья {exampleMetric?.code}</small>
  </div> : undefined;
  const exampleSteps: TutorialStep[] = [
    { target: "example-status", title: "Дождитесь результата", text: "Документы обрабатываются. Следующий шаг откроется, когда будут готовы суммы и источники расчёта.",
      complete: exampleReady, waitingText: current?.status === "failed" ? "Обработка прервана. Нажмите «Повторить обработку» или выйдите из обучения." : "Дождитесь завершения сверки.", successText: "Расчёт готов — можно исследовать результат." },
    { target: "example-filter", title: "Оставьте только расхождения", text: "Выберите фильтр «Расхождения», чтобы увидеть показатели, где сумма отчёта отличается от суммы по документам.",
      complete: filter === "MISMATCH", waitingText: "Нажмите «Расхождения» в выделенном фильтре.", successText: "Фильтр выбран. Найдём проблемную статью." },
    { target: detail?.code === exampleMetric?.code && detail ? "example-calculation" : "example-article", title: "Откройте статью с расхождением", text: "Нажмите на выделенную статью затрат. В её расчёте видны исходная сумма КФЗ, сумма по документам и разница.",
      complete: !!example?.article && example.article === exampleMetric?.code, waitingText: "Откройте выделенную строку статьи.", successText: "Расчёт статьи открыт. Проверим источники сумм." },
    { target: source?.doc.role === "report" ? sourceImageEvidence ? "example-evidence-view" : "example-evidence" : "example-report",
      anchor: source?.doc.role === "report" && sourceImageEvidence ? "example-evidence" : undefined,
      focusPadding: sourceImageEvidence ? 0 : undefined, title: "Проверьте сумму в КФЗ",
      text: source?.doc.role === "report" ? "Сравните выделенную сумму с указанной ниже. Над сканом можно изменить масштаб или открыть всю страницу."
        : "Нажмите «Посмотреть значение в КФЗ». Откроется скан с фрагментом, из которого прочитана сумма отчёта.",
      content: source?.doc.role === "report" ? exampleSourceReadout : undefined,
      complete: !!example?.reportOpened, waitingText: "Откройте исходный отчёт по выделенной кнопке.", successText: "Сумма открыта. Далее — первичный документ." },
    { target: source?.doc.role === "primary" ? sourceImageEvidence ? "example-evidence-view" : "example-evidence" : "example-primary",
      anchor: source?.doc.role === "primary" && sourceImageEvidence ? "example-evidence" : undefined,
      focusPadding: sourceImageEvidence ? 0 : undefined, title: "Откройте первичный документ",
      text: source?.doc.role === "primary" ? "Сравните выделенную сумму с указанной ниже. Это одно слагаемое полной суммы расходов по статье."
        : "Откройте выделенное слагаемое расчёта. Это одна операция: полная сумма по первичке складывается из всех учтённых документов статьи.",
      content: source?.doc.role === "primary" ? exampleSourceReadout : undefined,
      complete: !!example?.primaryDocument, waitingText: "Нажмите на выделенный документ в расчёте.", successText: "Подтверждающий документ открыт. Осталось сравнить суммы." },
    { target: "example-calculation", title: "Что означает расхождение?", text: "Сравните сумму отчёта с суммой по документам. Выберите верное объяснение — после этого можно завершить обучение.",
      complete: answerCorrect, waitingText: example?.answer ? "Пока неверно. Разница — сумма в отчёте минус сумма по документам. Сравните значения ещё раз." : "Выберите ответ ниже.",
      successText: "Верно! Вы нашли расхождение и проверили его источники.",
      content: <ExampleQuestion actual={exampleMetric?.actual ?? null} expected={exampleMetric?.expected ?? null}
        answer={example?.answer ?? null} onAnswer={(answer) => setExample((value) => value ? { ...value, answer } : value)} /> },
  ];
  const changeExampleStep = (step: number) => {
    if (!example || step < 0 || step >= exampleSteps.length || Math.abs(step - example.step) !== 1) return;
    if (step > example.step && exampleSteps[example.step].complete === false) return;
    setExample({ ...example, step });
    setSource(null);
    setTab("checks");
    if (step <= 1) setDetail(null);
    if (step === 1 && example.step < 1) setFilter("all");
    if (step >= 2) {
      setFilter("MISMATCH");
      setDetail(step > 2 || example.article ? exampleMetric || null : null);
    }
    if (step === 3 && example.reportOpened && report && exampleMetric?.report_evidence) {
      setSource({ doc: report, evidence: exampleMetric.report_evidence });
    }
    if (step === 4 && example.primaryDocument && exampleMetric) {
      const doc = docs.find((d) => d.id === example.primaryDocument);
      const term = exampleMetric.terms.find((t) => t.document_id === example.primaryDocument);
      if (doc && term) setSource({ doc, evidence: term.evidence });
    }
  };
  const finishExample = () => {
    if (!example || example.step !== 5 || !exampleReady || !example.article || !example.reportOpened || !example.primaryDocument || !answerCorrect) return;
    const completed = { article: example.article, difference: rub(exampleMetric?.delta ?? null) };
    cancelExample();
    setExampleSuccess(completed);
  };
  const primaryMetrics =
    result?.metrics.filter((m) => m.code !== "total") || [];
  const mismatch = primaryMetrics.filter((m) => m.status === "MISMATCH").length;
  const matched = primaryMetrics.filter((m) => m.status === "MATCH").length;
  const unverified = primaryMetrics.filter(
    (m) => !["MATCH", "MISMATCH"].includes(m.status),
  ).length;
  const total = result?.metrics.find((m) => m.code === "total");
  const hasMismatch = mismatch > 0 || total?.status === "MISMATCH";
  const showMetrics = (value: string) => {
    setTab("checks");
    setFilter(value);
    requestAnimationFrame(() =>
      document.getElementById("metrics-panel")?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      }),
    );
  };
  const caseLabels: Record<string, string> = {
    completed: "Завершена",
    running: "Выполняется",
    queued: "В очереди",
    failed: "Ошибка",
    draft: "Черновик",
  };
  const filteredCases = cases.filter((item) =>
    `${item.title} ${item.context.contract}`
      .toLowerCase()
      .includes(caseQuery.toLowerCase()),
  );
  const filteredDocs = docs.filter((d) =>
    d.name.toLowerCase().includes(search.toLowerCase()),
  );
  const showWelcome = !selected && !current && cases.length === 0;
  const visibleMetrics =
    result?.metrics.filter(
      (m) =>
        filter === "all" ||
        (filter === "unverified"
          ? !["MATCH", "MISMATCH"].includes(m.status)
          : m.status === filter),
    ) || [];

  return (
    <div className="shell" ref={shell}>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          aria-label="Все проверки"
          onClick={(e) => {
            e.preventDefault();
            overview();
          }}
        >
          <span className="brand-icon">
            <Layers3 size={25} />
          </span>
          сверка<span className="brand-label">workspace</span>
        </a>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <button
          className={"nav " + (tab === "checks" ? "active" : "")}
          onClick={overview}
        >
          <FileCheck2 size={18} />
          Проверки<span className="nav-count">{cases.length}</span>
        </button>
        <button
          className={"nav " + (tab === "documents" ? "active" : "")}
          disabled={!current}
          onClick={() => setTab("documents")}
        >
          <FolderOpen size={18} />
          Документы
        </button>
        <button
          className={"nav " + (tab === "history" ? "active" : "")}
          disabled={!current}
          onClick={() => setTab("history")}
        >
          <History size={18} />
          История запусков
        </button>
        <button className="nav" onClick={() => setFixturesOpen(true)}>
          <Layers3 size={18} />
          Примеры проверок
        </button>
        <div className="sidebar-section">
          <span>ПОСЛЕДНИЕ ПРОВЕРКИ</span>
          <div className="sidebar-section-actions">
            <button aria-label="Очистить последние проверки" title={clearableCases.length ? "Очистить последние проверки" : "Нет проверок для очистки"}
              disabled={!clearableCases.length || busy} onClick={openClearChecks}>
              <Trash2 size={15} />
            </button>
            <button aria-label="Новая проверка" onClick={() => openNew()}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <label className="case-search">
          <Search size={15} />
          <input
            aria-label="Найти проверку"
            placeholder="Название или договор"
            value={caseQuery}
            onChange={(e) => setCaseQuery(e.target.value)}
          />
        </label>
        <div className="case-list">
          {filteredCases.map((c) => (
            <div className={"case-list-row " + (c.id === selected ? "selected" : "")} key={c.id}>
            <button
              className={"case-link " + (c.id === selected ? "selected" : "")}
              onClick={() => choose(c.id)}
              title={c.title}
            >
              <span
                className={
                  "case-dot " + (c.status === "completed" ? "done" : "")
                }
              />
              <span className="case-link-info">
                {c.title}
                <small>
                  {caseLabels[c.status] || c.status}
                  {c.created_at
                    ? " · " + new Date(c.created_at).toLocaleDateString("ru-RU")
                    : ""}
                </small>
              </span>
            </button>
            <button className="case-delete" aria-label={`Удалить проверку «${c.title}»`}
              title={["queued", "running"].includes(c.status) ? "Дождитесь завершения проверки" : "Удалить проверку"}
              disabled={busy || ["queued", "running"].includes(c.status)} onClick={() => openDeleteCheck(c)}>
              <Trash2 size={15} />
            </button>
            </div>
          ))}
          {!cases.length && (
            <p className="sidebar-empty">Здесь появятся ваши проверки</p>
          )}
          {!!cases.length && !filteredCases.length && (
            <p className="sidebar-empty">Проверки не найдены</p>
          )}
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumbs">
            <button onClick={overview}>Все проверки</button>
            <ChevronRight size={14} />
            <strong>
              {current
                ? tab === "documents"
                  ? "Документы проверки"
                  : tab === "history"
                    ? "История проверки"
                    : "Результаты"
                : "Рабочее пространство"}
            </strong>
          </div>
        </header>
        <div className="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">ПРОВЕРКА ДОСТОВЕРНОСТИ ОТЧЁТНОСТИ</div>
              <h1>
                {current
                  ? current.title
                  : selected
                    ? "Открываем проверку…"
                    : "Сверка отчётности"}
              </h1>
              <p>
                {current
                  ? "Сопоставление показателей КФЗ с первичными документами"
                  : "Загрузите отчёт и первичные документы. Мы соберём расчёт и покажем источники каждого результата."}
              </p>
            </div>
            <div className="heading-actions">
              {!showWelcome && <button className="button example-trigger" onClick={openExample} title="Учебный пример с готовыми документами">
                <GraduationCap size={17} />Учебный пример
              </button>}
              <button
                className="button fixtures-mobile-trigger"
                onClick={() => setFixturesOpen(true)}
              >
                <Layers3 size={17} />
                Примеры проверок
              </button>
              <button
                className="button primary"
                aria-label="Новая проверка"
                onClick={() => openNew()}
              >
                <Plus size={17} />
                Новая проверка
              </button>
            </div>
          </div>
          {error && (
            <div role="alert" className="error-banner">
              <CircleAlert size={18} />
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Закрыть ошибку">
                <X size={18} />
              </button>
            </div>
          )}
          {example?.caseId && selected === example.caseId && <section className="example-status" data-tutorial="example-status" aria-label="Учебная проверка">
            <strong>Учебный комплект</strong>
            <span role="status">{exampleReady ? "Проверка завершена. Суммы и источники готовы."
              : current?.status === "failed" ? "Не удалось завершить обработку."
              : current?.status === "completed" ? "В результате не найдены все данные для учебного примера."
              : "Выполняется сверка документов…"}</span>
            {(current?.status === "failed" || (current?.status === "completed" && !exampleReady)) &&
              <button className="button" disabled={busy} onClick={start}>Повторить обработку</button>}
          </section>}
          {!current && selected ? (
            <div className="panel empty-small" role="status">
              <Loader2 className="spin" />
              <p>Загружаем документы и результаты…</p>
            </div>
          ) : !current ? (
            <>
              {showWelcome && (
                <div className="welcome">
                  <div className="welcome-learning-icon" aria-hidden="true">
                    <GraduationCap size={28} />
                  </div>
                  <span className="eyebrow">ПРАКТИКА С ПОДСКАЗКАМИ</span>
                  <h2>Начните с учебного примера</h2>
                  <p className="welcome-description">
                    Разберитесь, как проходит проверка, на готовом комплекте документов.{" "}
                    <br />
                    Мы поможем найти расхождение и проверить его по исходным файлам.
                  </p>
                  <div className="welcome-learning-path" aria-label="Чему вы научитесь">
                    <span><Files size={16} />Выбрать документы</span>
                    <span><Search size={16} />Найти расхождение</span>
                    <span><FileCheck2 size={16} />Проверить источники</span>
                  </div>
                  <div className="welcome-actions">
                    <button
                      className="button primary"
                      onClick={openExample}
                    >
                      <GraduationCap size={18} />
                      Пройти учебный пример
                    </button>
                    <button
                      className="button"
                      disabled={busy}
                      onClick={() => openNew()}
                    >
                      <Upload size={17} />
                      Загрузить свои документы
                    </button>
                  </div>
                  <p className="welcome-note">Учебный пример можно прервать в любой момент.</p>
                </div>
              )}
              {!!cases.length && (
                <section className="panel overview-cases">
                  <div className="panel-heading">
                    <h2>
                      Ваши проверки{" "}
                      <span className="subtle">{cases.length}</span>
                    </h2>
                    <div className="overview-case-tools">
                      <label className="search">
                        <Search size={16} />
                        <input
                          aria-label="Поиск по проверкам"
                          placeholder="Название или договор"
                          value={caseQuery}
                          onChange={(e) => setCaseQuery(e.target.value)}
                        />
                      </label>
                      <button className="button clear-checks-trigger" disabled={!clearableCases.length || busy} onClick={openClearChecks}
                        aria-label="Очистить последние проверки"><Trash2 size={16} />Очистить</button>
                    </div>
                  </div>
                  {filteredCases.map((c) => (
                    <div className="overview-case-row" key={c.id}>
                    <button
                      className="overview-case"
                      onClick={() => choose(c.id)}
                    >
                      <FileCheck2 size={21} />
                      <div>
                        <strong>{c.title}</strong>
                        <small>
                          Договор {c.context.contract} · Этап {c.context.stage}
                          {c.created_at
                            ? " · " +
                              new Date(c.created_at).toLocaleString("ru-RU")
                            : ""}
                        </small>
                      </div>
                      <span className={"case-status " + c.status}>
                        {caseLabels[c.status] || c.status}
                      </span>
                      <ChevronRight size={17} />
                    </button>
                    <button className="case-delete" aria-label={`Удалить проверку «${c.title}»`}
                      title={["queued", "running"].includes(c.status) ? "Дождитесь завершения проверки" : "Удалить проверку"}
                      disabled={busy || ["queued", "running"].includes(c.status)} onClick={() => openDeleteCheck(c)}>
                      <Trash2 size={17} />
                    </button>
                    </div>
                  ))}
                  {!filteredCases.length && (
                    <div className="empty-small">
                      Ничего не найдено. Попробуйте другое название или номер
                      договора.
                    </div>
                  )}
                </section>
              )}
            </>
          ) : (
            <>
              <div className="context-bar">
                <span>
                  <FileText size={15} />
                  <small>Договор</small>
                  <strong>{current.context.contract}</strong>
                </span>
                <i />
                <span>
                  <small>Этап</small>
                  <strong>{current.context.stage}</strong>
                </span>
                <i />
                <span>
                  <Clock3 size={15} />
                  <strong>
                    {dt(current.context.period_start)} —{" "}
                    {dt(current.context.period_end)}
                  </strong>
                </span>
                <div className="context-right">
                  <span
                    className={"status-dot " + (running ? "working" : "")}
                  />
                  {running
                    ? "Обрабатываем документы"
                    : current.status === "completed"
                      ? "Проверка завершена"
                      : current.status === "failed"
                        ? "Ошибка обработки"
                        : "Комплект документов"}
                  <button className="icon-button delete-current-check" aria-label="Удалить эту проверку"
                    title={running ? "Дождитесь завершения проверки" : "Удалить проверку"}
                    disabled={busy || running} onClick={() => openDeleteCheck(current)}><Trash2 size={17} /></button>
                </div>
              </div>
              {result && tab === "checks" && (
                <section
                  className={
                    "result-summary " +
                    (hasMismatch
                      ? "attention"
                      : unverified || total?.status !== "MATCH"
                        ? "incomplete"
                        : "confirmed")
                  }
                  aria-label="Итог сверки"
                >
                  <span className="result-summary-icon">
                    {hasMismatch || unverified ? (
                      <CircleAlert size={25} />
                    ) : (
                      <ShieldCheck size={25} />
                    )}
                  </span>
                  <div>
                    <span className="eyebrow">ИТОГ СВЕРКИ ДОКУМЕНТОВ</span>
                    <h2>
                      {hasMismatch
                        ? "Есть расхождения в отчёте"
                        : unverified || total?.status !== "MATCH"
                          ? "Для вывода нужны дополнительные данные"
                          : "Проверяемые суммы подтверждены"}
                    </h2>
                    <p>
                      {hasMismatch
                        ? total?.delta == null
                          ? "В отдельных статьях есть расхождения. Для общего итога недостаточно данных."
                          : Number(total.delta) === 0
                            ? "Суммы отдельных статей отличаются, хотя общий итог совпадает."
                            : "Разница между отчётом и подтверждающими документами. Откройте статью, чтобы увидеть расчёт."
                        : "Вывод относится к предоставленному комплекту. Непроверенные показатели перечислены в границах проверки."}
                    </p>
                  </div>
                  {hasMismatch && total?.delta != null && (
                    <div className="result-summary-amount">
                      <small>Разница по итогу</small>
                      <strong>
                        {Number(total.delta) > 0 ? "+" : ""}
                        {rub(total.delta)} ₽
                      </strong>
                    </div>
                  )}
                  <button
                    className="button"
                    onClick={() =>
                      showMetrics(
                        hasMismatch
                          ? "MISMATCH"
                          : unverified
                            ? "unverified"
                            : "all",
                      )
                    }
                  >
                    {hasMismatch
                      ? "Показать расхождения"
                      : unverified
                        ? "Что проверить"
                        : "К показателям"}
                    <ArrowRight size={16} />
                  </button>
                </section>
              )}
              {current.fixture_comparison && tab === "checks" && (
                <FixtureComparisonPanel
                  comparison={current.fixture_comparison}
                />
              )}
              {running && (
                <div className="progress-card">
                  <Loader2 className="spin" size={20} />
                  <div>
                    <strong>
                      {current.runs?.[0]?.message || "Подготовка документов"}
                    </strong>
                    <div className="progress-track">
                      <span
                        style={{
                          width: (current.runs?.[0]?.progress || 3) + "%",
                        }}
                      />
                    </div>
                  </div>
                  <span>{current.runs?.[0]?.progress || 0}%</span>
                </div>
              )}
              {current.status === "failed" && (
                <div className="error-banner">
                  {current.runs?.[0]?.message}
                  <button className="button" onClick={start}>
                    Повторить
                  </button>
                </div>
              )}
              {result && (
                <div className="stats">
                  <button className="stat" onClick={() => showMetrics("MATCH")}>
                    <span className="stat-icon green">
                      <CheckCheck size={21} />
                    </span>
                    <div>
                      <span>Подтверждено</span>
                      <strong>
                        {matched}
                        <small>из {primaryMetrics.length} статей</small>
                      </strong>
                    </div>
                  </button>
                  <button
                    className="stat"
                    onClick={() => showMetrics("MISMATCH")}
                  >
                    <span className="stat-icon orange">
                      <CircleAlert size={21} />
                    </span>
                    <div>
                      <span>Расхождения</span>
                      <strong>
                        {mismatch}
                        <small>
                          {mismatch === 0 && total?.status === "MISMATCH"
                            ? "ошибка общего итога"
                            : "по статьям затрат"}
                        </small>
                      </strong>
                    </div>
                  </button>
                  <button
                    className="stat"
                    onClick={() => showMetrics("unverified")}
                  >
                    <span className="stat-icon gray">
                      <Search size={21} />
                    </span>
                    <div>
                      <span>Недостаточно данных</span>
                      <strong>
                        {unverified}
                        <small>статей затрат</small>
                      </strong>
                    </div>
                  </button>
                  <button className="stat" onClick={() => setTab("documents")}>
                    <span className="stat-icon blue">
                      <Files size={21} />
                    </span>
                    <div>
                      <span>Первичные документы</span>
                      <strong>
                        {result.summary.included_documents}
                        <small>
                          из {docs.filter((d) => d.role === "primary").length}{" "}
                          учтено
                        </small>
                      </strong>
                    </div>
                  </button>
                </div>
              )}
              <div className="tabs">
                <button
                  className={tab === "checks" ? "active" : ""}
                  onClick={() => setTab("checks")}
                >
                  Результаты сверки
                  {result && <span>{result.metrics.length}</span>}
                </button>
                <button
                  className={tab === "documents" ? "active" : ""}
                  onClick={() => setTab("documents")}
                >
                  Документы<span>{docs.length}</span>
                </button>
                <button
                  className={tab === "history" ? "active" : ""}
                  onClick={() => setTab("history")}
                >
                  История
                </button>
                <div className="tab-actions">
                  {result && (
                    <a
                      className="text-button"
                      href={`/api/cases/${selected}/runs/${current.active_run_id}/export?format=csv`}
                    >
                      <ArrowDownToLine size={16} />
                      Экспорт CSV
                    </a>
                  )}
                  <button
                    className="text-button"
                    disabled={running || busy}
                    onClick={start}
                  >
                    <RefreshCw size={15} />
                    Пересчитать
                  </button>
                </div>
              </div>
              {tab === "checks" &&
                (result ? (
                  <>
                    <section className="panel" id="metrics-panel">
                      <div className="panel-heading">
                        <h2>Показатели отчёта</h2>
                        <div
                          className="filters"
                          aria-label="Фильтр результатов"
                          data-tutorial="example-filter"
                        >
                          {[
                            ["all", "Все"],
                            ["MISMATCH", "Расхождения"],
                            ["MATCH", "Подтверждено"],
                            ["unverified", "Нужны данные"],
                          ].map(([v, l]) => (
                            <button
                              key={v}
                              className={filter === v ? "active" : ""}
                              aria-pressed={filter === v}
                              onClick={() => setFilter(v)}
                            >
                              {l}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="table-scroll">
                        <table className="metrics-table">
                          <thead>
                            <tr>
                              <th>Статья затрат</th>
                              <th>В отчёте, ₽</th>
                              <th>По документам, ₽</th>
                              <th>Разница, ₽</th>
                              <th>Результат</th>
                              <th />
                            </tr>
                          </thead>
                          <tbody>
                            {visibleMetrics.map((m) => (
                              <tr
                                key={m.code}
                                className={
                                  (m.status === "MISMATCH"
                                    ? "has-issue "
                                    : "") + (m.code === "total" ? "total" : "")
                                }
                                data-tutorial={m.code === exampleMetric?.code ? "example-article" : undefined}
                                onClick={() => openMetric(m)}
                                tabIndex={0}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" || e.key === " ") {
                                    e.preventDefault();
                                    openMetric(m);
                                  }
                                }}
                              >
                                <td>
                                  <span className="article-code">
                                    {m.code === "total" ? "∑" : m.code}
                                  </span>
                                  <strong>{m.name}</strong>
                                </td>
                                <td className="number">{rub(m.actual)}</td>
                                <td className="number">{rub(m.expected)}</td>
                                <td
                                  className={
                                    "number " +
                                    (Number(m.delta) ? "delta" : "muted")
                                  }
                                >
                                  {Number(m.delta) > 0 ? "+" : ""}
                                  {rub(m.delta)}
                                </td>
                                <td>
                                  <Badge status={m.status} />
                                </td>
                                <td>
                                  <ChevronRight size={16} />
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {!visibleMetrics.length && (
                          <div className="empty-small">
                            Показателей с выбранным статусом нет
                          </div>
                        )}
                      </div>
                      <div className="table-foot">
                        <span>
                          <ShieldCheck size={14} />
                          Расчёт по уникальным документам указанного договора и
                          периода
                        </span>
                        <span>Точность до копейки</span>
                      </div>
                    </section>
                    <div className="lower-grid">
                      <section className="panel">
                        <div className="panel-heading">
                          <h2>Контроль комплекта</h2>
                          <span className="subtle">
                            Всего: {result.findings.length}
                          </span>
                        </div>
                        {result.findings.length ? (
                          result.findings.map((f, i) => (
                            <button
                              className="finding"
                              key={i}
                              onClick={() => showSource(f.document_id)}
                            >
                              <span className="finding-icon">
                                <Files size={17} />
                              </span>
                              <div>
                                <strong>{labels[f.type] || f.type}</strong>
                                <span>{f.name || f.detail}</span>
                              </div>
                              <ChevronRight size={16} />
                            </button>
                          ))
                        ) : (
                          <div className="empty-small">
                            Замечаний к комплекту нет
                          </div>
                        )}
                      </section>
                      <section className="panel">
                        <div className="panel-heading">
                          <h2>Границы проверки</h2>
                          <span className="subtle">
                            {result.unverified.length} вне расчёта
                          </span>
                        </div>
                        {result.unverified.map((m) => (
                          <div className="unverified" key={m.code}>
                            <span className="tiny-dot" />
                            <div>
                              <strong>{m.name}</strong>
                              <p>{m.reason}</p>
                            </div>
                          </div>
                        ))}
                      </section>
                    </div>
                    <p className="scope-note">
                      <ShieldCheck size={14} />
                      {result.summary.scope}
                    </p>
                  </>
                ) : (
                  <section className="panel empty-small">
                    <Loader2 size={25} className={running ? "spin" : ""} />
                    <h2>
                      {running
                        ? "Сопоставляем отчёт с источниками"
                        : "Документы готовы к проверке"}
                    </h2>
                    <p>
                      {running
                        ? "Результаты появятся после завершения обработки."
                        : "Нажмите «Пересчитать», чтобы выполнить сверку."}
                    </p>
                  </section>
                ))}
              {tab === "documents" && (
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Документы комплекта</h2>
                    <label className="search">
                      <Search size={16} />
                      <input
                        placeholder="Найти документ"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                  </div>
                  {!filteredDocs.length && (
                    <div className="empty-small">
                      <Search size={24} />
                      <h3>Документы не найдены</h3>
                      <p>Попробуйте часть имени файла.</p>
                      <button className="button" onClick={() => setSearch("")}>
                        Сбросить поиск
                      </button>
                    </div>
                  )}
                  {filteredDocs.map((d) => (
                    <button
                      key={d.id}
                      className="document-row"
                      onClick={() =>
                        setSource({
                          doc: d,
                          evidence: d.extraction?.amount_evidence,
                        })
                      }
                    >
                      <span className="file-icon">
                        <FileText size={20} />
                        <small>{d.name.split(".").pop()}</small>
                      </span>
                      <div>
                        <strong>{d.name}</strong>
                        <p>
                          {d.role === "report"
                            ? "Итоговый отчёт"
                            : d.extraction?.contract || "Первичный документ"}
                          {d.extraction?.article
                            ? " · " + articles[d.extraction.article]
                            : ""}
                        </p>
                      </div>
                      <span className="document-amount">
                        {d.extraction?.amount
                          ? rub(d.extraction.amount) + " ₽"
                          : ""}
                      </span>
                      {d.role === "report" ? (
                        <span className="badge report">КФЗ</span>
                      ) : (
                        <Badge status={d.disposition || "NEEDS_REVIEW"} />
                      )}
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </section>
              )}
              {tab === "history" && (
                <section className="panel">
                  <div className="panel-heading">
                    <h2>История запусков и уточнений</h2>
                  </div>
                  {current.runs?.map((r, i) => (
                    <div className="history-row" key={r.id}>
                      <span className="stat-icon blue">
                        <History size={18} />
                      </span>
                      <div>
                        <strong>Запуск {current.runs!.length - i}</strong>
                        <p>
                          {new Date(r.created_at).toLocaleString("ru-RU")} ·{" "}
                          {r.message}
                        </p>
                      </div>
                      {r.status === "completed" && (
                        <a
                          className="text-button"
                          href={`/api/cases/${selected}/runs/${r.id}/export`}
                        >
                          Результат JSON
                          <ArrowDownToLine size={15} />
                        </a>
                      )}
                    </div>
                  ))}
                  {current.reviews?.map((r) => (
                    <div className="history-row" key={r.id}>
                      <span className="stat-icon orange">
                        <SlidersHorizontal size={18} />
                      </span>
                      <div>
                        <strong>Уточнение пользователя</strong>
                        <p>{r.reason}</p>
                        <code>
                          {JSON.stringify(r.before)} →{" "}
                          {JSON.stringify(r.changes)}
                        </code>
                      </div>
                    </div>
                  ))}
                </section>
              )}
            </>
          )}
          <footer>
              <span>Сверка</span>
            <span>MVP 1.0</span>
          </footer>
        </div>
      </main>
      {newOpen && (
        <NewCaseModal
          initialTutorial={newTutorial}
          onClose={() => setNewOpen(false)}
          onDone={(id) => {
            setNewOpen(false);
            choose(id);
          }}
        />
      )}
      {fixturesOpen && (
        <FixtureCatalog
          onClose={() => {
            setFixturesOpen(false);
            refresh().catch((e) => setError(e.message));
          }}
          onDone={(id) => {
            setFixturesOpen(false);
            choose(id);
          }}
        />
      )}
      {detail && result && (
        <div className="overlay" onClick={() => setDetail(null)}>
          <section
            className="detail-panel"
            ref={detailDialog}
            role="dialog"
            aria-modal="true"
            aria-label="Расчёт показателя"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close"
              aria-label="Закрыть расчёт"
              onClick={() => setDetail(null)}
            >
              <X />
            </button>
            <span className="eyebrow">РАСЧЁТ ПОКАЗАТЕЛЯ · {detail.code}</span>
            <h2>{detail.name}</h2>
            <Badge status={detail.status} />
            <div className="detail-values" data-tutorial="example-calculation">
              <div>
                <small>В отчёте</small>
                <strong>{rub(detail.actual)} ₽</strong>
              </div>
              <div>
                <small>Ожидается</small>
                <strong>{rub(detail.expected)} ₽</strong>
              </div>
              <div>
                <small>Разница</small>
                <strong className={Number(detail.delta) ? "delta" : ""}>
                  {rub(detail.delta)} ₽
                </strong>
              </div>
            </div>
            {detail.reason && (
              <p className="notice">
                {detail.reason}
                {detail.confirmed_subtotal &&
                  ` Подтверждённая часть: ${rub(detail.confirmed_subtotal)} ₽.`}
              </p>
            )}
            {report && detail.report_evidence && (
              <button
                className="report-link"
                data-tutorial="example-report"
                onClick={() => showSource(report.id, detail.report_evidence)}
              >
                <FileText size={18} />
                Посмотреть значение в КФЗ
                <ArrowRight size={17} />
              </button>
            )}
            <h3>Источники расчёта</h3>
            {detail.code === "total"
              ? result.metrics
                  .filter((m) => m.code !== "total")
                  .map((m) => (
                    <button
                      className="term"
                      key={m.code}
                      onClick={() => openMetric(m)}
                    >
                      <div>
                        <strong>
                          {m.code} · {m.name}
                        </strong>
                        <small>{labels[m.status]}</small>
                      </div>
                      <strong>{rub(m.expected)} ₽</strong>
                      <ChevronRight size={17} />
                    </button>
                  ))
              : detail.terms.map((t, index) => (
                  <button
                    className="term"
                    data-tutorial={index === 0 ? "example-primary" : undefined}
                    key={t.document_id}
                    onClick={() => showSource(t.document_id, t.evidence)}
                  >
                    <span className="file-icon">
                      <FileText size={19} />
                    </span>
                    <div>
                      <strong>{t.name}</strong>
                      <small>
                        {t.evidence?.sheet
                          ? `${t.evidence.sheet}!${t.evidence.range}`
                          : t.evidence?.page
                            ? `Страница ${t.evidence.page}`
                            : "Фрагмент документа"}
                        {t.reviewed ? " · Уточнено пользователем" : ""}
                      </small>
                    </div>
                    <strong>{rub(t.amount)} ₽</strong>
                    <ChevronRight size={17} />
                  </button>
                ))}
            {!detail.terms.length && detail.code !== "total" && (
              <p className="muted">Подтверждающие операции не найдены.</p>
            )}
            <p className="detail-note">
              Ожидаемое значение — сумма уникальных операций после проверки
              договора, периода и назначения расходов.
            </p>
          </section>
        </div>
      )}
      {source && selected && (
        <SourcePanel
          source={source}
          caseId={selected}
          focusEvidence={!!example && (example.step === 3 || example.step === 4)}
          onClose={() => setSource(null)}
          onReviewed={async () => {
            setSource(null);
            setDetail(null);
            await refresh();
          }}
        />
      )}
      {example?.step === -1 && <NewCaseModal training onClose={cancelExample} onDone={(id) => {
        setExample((value) => value ? { ...value, caseId: id, step: 0 } : value);
        choose(id);
      }} />}
      {example && example.step >= 0 && <CheckTutorial root={shell} steps={exampleSteps} step={example.step} stepOffset={5} totalSteps={11} label="Учебный пример" exitLabel="Выйти"
        onStepChange={changeExampleStep} onClose={cancelExample} onFinish={finishExample} />}
      {clearChecks && <ClearChecksDialog count={clearChecks.ids.length} activeCount={clearChecks.activeCount}
        caseTitle={clearChecks.caseTitle}
        onClose={() => setClearChecks(null)} onConfirm={confirmClearChecks} />}
      {exampleSuccess && <TaskExampleSuccess {...exampleSuccess} onClose={() => setExampleSuccess(null)}
        onNew={() => { setExampleSuccess(null); openNew(); }} />}
    </div>
  );
}

function FixtureComparisonPanel({
  comparison,
}: {
  comparison: FixtureComparison;
}) {
  const value = (
    v: FixtureDifference["actual"],
    kind: FixtureDifference["kind"],
  ) => {
    if (v === null) return "Не определено";
    if (kind === "money") return rub(String(v)) + " ₽";
    if (kind === "status") return labels[String(v)] || String(v);
    if (kind === "boolean") return v ? "Да" : "Нет";
    return String(v);
  };
  if (!comparison.available)
    return (
      <div className="fixture-comparison unavailable">
        <CircleAlert size={19} />
        <p>{comparison.message}</p>
      </div>
    );
  return (
    <section
      className={
        "fixture-comparison " + (comparison.matches ? "confirmed" : "differs")
      }
      aria-label="Сравнение с эталоном"
    >
      <div className="fixture-comparison-heading">
        {comparison.matches ? (
          <CheckCheck size={23} />
        ) : (
          <CircleAlert size={23} />
        )}
        <div>
          <span className="eyebrow">
            ТЕСТОВЫЙ СЦЕНАРИЙ · {comparison.title || comparison.fixture_id}
          </span>
          <h2>
            {comparison.matches
              ? "Тестовый сценарий пройден"
              : "Тестовый сценарий выявил отличия"}
          </h2>
          <p>
            {comparison.matches
              ? "Поведение соответствует эталону теста. Финансовый итог показан выше."
              : "Полученный результат отличается от эталона теста. Посмотрите подробности ниже."}
          </p>
        </div>
      </div>
      {comparison.known_limitation && (
        <p className="fixture-limitation">
          <strong>Известное ограничение MVP:</strong>{" "}
          {comparison.known_limitation}
        </p>
      )}
      {comparison.differences.length > 0 && (
        <details className="fixture-differences">
          <summary>Показать отличия ({comparison.differences.length})</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Проверяемый показатель</th>
                  <th>Эталон</th>
                  <th>Получено</th>
                </tr>
              </thead>
              <tbody>
                {comparison.differences.map((d, i) => (
                  <tr key={i}>
                    <td>
                      {d.label.replace(
                        /Замечания · ([A-Z_]+)/,
                        (_, code: string) =>
                          "Замечания · " + (labels[code] || code),
                      )}
                    </td>
                    <td>{value(d.expected, d.kind)}</td>
                    <td>{value(d.actual, d.kind)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}

function FixtureCatalog({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: (id: string) => void;
}) {
  const [items, setItems] = useState<Fixture[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [chosen, setChosen] = useState(""),
    [showContext, setShowContext] = useState(false),
    [busy, setBusy] = useState(false),
    [rejected, setRejected] = useState<FixtureLaunch | null>(null),
    [batch, setBatch] = useState<FixtureBatch | null>(null),
    [batchError, setBatchError] = useState(""),
    [view, setView] = useState("catalog");
  const dialog = useDialog(onClose, busy);
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([
      api<Fixture[]>("/fixtures"),
      api<FixtureBatch | null>("/fixture-batches/latest"),
    ])
      .then(([catalog, latest]) => {
        if (cancelled) return;
        if (catalog.status === "fulfilled") setItems(catalog.value);
        else setError(catalog.reason.message);
        if (latest.status === "fulfilled") {
          setBatch(latest.value);
          if (latest.value?.status === "running") setView("batch");
        } else setBatchError(latest.reason.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (!batch || batch.status === "completed") return;
    let cancelled = false;
    let timer: number;
    const id = batch.id;
    const poll = async () => {
      try {
        const next = await api<FixtureBatch>(`/fixture-batches/${id}`);
        if (!cancelled) {
          setBatch(next);
          setBatchError("");
        }
      } catch (e) {
        if (!cancelled) setBatchError((e as Error).message);
      } finally {
        if (!cancelled) timer = window.setTimeout(poll, 1500);
      }
    };
    timer = window.setTimeout(poll, 1000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [batch?.id, batch?.status]);
  const visible = items.filter(
    (item) =>
      (filter === "all" ||
        (filter === "limitations"
          ? !!item.known_limitation
          : !item.known_limitation)) &&
      `${item.id} ${item.title} ${item.description}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const active = visible.find((item) => item.id === chosen) || visible[0];
  const select = (id: string) => {
    setChosen(id);
    setShowContext(false);
    setRejected(null);
    setError("");
  };
  const launch = async () => {
    if (!active) return;
    setBusy(true);
    setError("");
    setRejected(null);
    try {
      const result = await api<FixtureLaunch>(`/fixtures/${active.id}/runs`, {
        method: "POST",
      });
      if (result.status === "queued" && result.case_id) onDone(result.case_id);
      else if (result.status === "rejected") setRejected(result);
      else throw new Error("Не удалось запустить пример");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const launchAll = async () => {
    setBusy(true);
    setError("");
    setBatchError("");
    setRejected(null);
    try {
      setBatch(await api<FixtureBatch>("/fixture-batches", { method: "POST" }));
      setView("batch");
    } catch (e) {
      setError((e as Error).message);
      // Another tab may already have started the same whole-catalog run.
      try {
        const latest = await api<FixtureBatch | null>(
          "/fixture-batches/latest",
        );
        if (latest?.status === "running") {
          setBatch(latest);
          setView("batch");
        }
      } catch {
        // The launch error remains visible; the catalog stays usable.
      }
    } finally {
      setBusy(false);
    }
  };
  const batchRunning = batch?.status === "running";
  return (
    <div className="overlay fixture-overlay">
      <section
        className="fixture-modal"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label="Примеры проверок"
      >
        <header className="fixture-modal-heading">
          <div>
            <span className="eyebrow">ПРИМЕРЫ ПРОВЕРОК</span>
            <h2>Готовые комплекты для проверки</h2>
            <p>
              Выберите пример, запустите проверку и сравните результат с ожидаемым.
            </p>
          </div>
          <button
            className="icon-button"
            aria-label="Закрыть примеры проверок"
            disabled={busy}
            onClick={onClose}
          >
            <X />
          </button>
        </header>
        <div className="fixture-tabs" aria-label="Раздел примеров проверок">
          <button
            className={view === "catalog" ? "active" : ""}
            disabled={busy}
            onClick={() => setView("catalog")}
          >
            Каталог
          </button>
          <button
            className={view === "batch" ? "active" : ""}
            disabled={busy || !batch}
            onClick={() => setView("batch")}
          >
            Все примеры{batch ? ` · ${batch.done}/${batch.total}` : ""}
          </button>
        </div>
        {view === "catalog" && (
          <div className="fixture-toolbar">
            <label className="search">
              <Search size={16} />
              <input
                autoFocus
                placeholder="Найти пример по названию или номеру"
                value={query}
                disabled={busy}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setRejected(null);
                }}
              />
            </label>
            <div className="filters">
              {[
                ["all", "Все"],
                ["supported", "Поддерживаются"],
                ["limitations", "Ограничения MVP"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  disabled={busy}
                  className={filter === id ? "active" : ""}
                  onClick={() => {
                    setFilter(id);
                    setRejected(null);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
        {(error || batchError) && (
          <p role="alert" className="fixture-error">
            {error || batchError}
          </p>
        )}
        {view === "batch" && batch ? (
          <FixtureBatchResults batch={batch} onOpen={onDone} />
        ) : (
          <div className="fixture-layout">
            <div className="fixture-list" aria-label="Список примеров">
              {loading ? (
                <div className="empty-small">
                  <Loader2 size={22} className="spin" />
                  <p>Загружаем каталог…</p>
                </div>
              ) : visible.length ? (
                visible.map((item) => (
                  <button
                    className={
                      "fixture-option " +
                      (item.id === active?.id ? "selected" : "")
                    }
                    key={item.id}
                    disabled={busy}
                    aria-pressed={item.id === active?.id}
                    onClick={() => select(item.id)}
                  >
                    <span className="fixture-number">
                      {item.origin === "task" ? "ТЗ" : item.id.slice(0, 2)}
                    </span>
                    <div>
                      <strong>{item.title}</strong>
                      <span>{item.description}</span>
                      {item.origin === "task" && (
                        <small className="task-fixture">Из задания</small>
                      )}
                      {item.known_limitation && <small>Ограничение MVP</small>}
                    </div>
                    {item.id === active?.id && <Check size={17} />}
                  </button>
                ))
              ) : (
                <div className="empty-small">
                  {items.length
                    ? "Примеры не найдены. Измените запрос или фильтр."
                    : "Готовые комплекты не установлены. Можно загрузить свои документы через «Новая проверка»."}
                </div>
              )}
            </div>
            <aside
              className={
                "fixture-description " +
                (showContext ? "expanded" : "collapsed")
              }
            >
              {active && (
                <>
                  <button
                    className="fixture-context-toggle"
                    aria-expanded={showContext}
                    aria-controls="fixture-context"
                    onClick={() => setShowContext(!showContext)}
                  >
                    <span>
                      <small>ПАРАМЕТРЫ ПРИМЕРА</small>
                      {active.title}
                    </span>
                    <ChevronRight size={18} />
                  </button>
                  <div id="fixture-context">
                    <span className="eyebrow">
                      {active.origin === "task"
                        ? "ИЗ ЗАДАНИЯ"
                        : `ПРИМЕР ${active.id.slice(0, 2)}`}
                    </span>
                    <h3>{active.title}</h3>
                    <p>{active.description}</p>
                    <dl>
                      <dt>Договор</dt>
                      <dd>{active.context.contract}</dd>
                      <dt>Этап</dt>
                      <dd>{active.context.stage}</dd>
                      <dt>Период</dt>
                      <dd>
                        {dt(active.context.period_start)} —{" "}
                        {dt(active.context.period_end)}
                      </dd>
                      <dt>Комплект</dt>
                      <dd>
                        {active.input_files} файлов ·{" "}
                        {active.context.complete_package
                          ? "заявлен полным"
                          : "полнота не подтверждена"}
                      </dd>
                    </dl>
                    {active.known_limitation ? (
                      <p className="fixture-scope">
                        <CircleAlert size={17} />
                        <span>
                          <strong>Известное ограничение</strong>
                          {active.known_limitation}
                        </span>
                      </p>
                    ) : (
                      <p className="fixture-scope supported">
                        <ShieldCheck size={17} />
                        <span>
                          Сценарий входит в проверку работы приложения на тестовых примерах.
                        </span>
                      </p>
                    )}
                    <p className="fixture-oracle-note">
                      После сверки появится сравнение с ожидаемым результатом.
                    </p>
                  </div>
                </>
              )}
            </aside>
          </div>
        )}
        {view === "catalog" && rejected && (
          <div
            className={
              "fixture-rejection " +
              (rejected.matches_expected ? "expected" : "unexpected")
            }
            role="status"
          >
            {rejected.matches_expected ? (
              <CheckCheck size={21} />
            ) : (
              <CircleAlert size={21} />
            )}
            <div>
              <strong>
                {rejected.matches_expected
                  ? "Повреждённый файл отклонён, как и ожидалось"
                  : "Результат загрузки отличается от эталона"}
              </strong>
              <p>
                {rejected.filename}: проверка формата отклонила загрузку. Код{" "}
                {rejected.actual_http_status}, ожидается{" "}
                {rejected.expected_http_status}. Сверка сумм не запускалась.
              </p>
            </div>
          </div>
        )}
        <footer className="fixture-modal-footer">
          <span>
            {view === "batch" && batch
              ? `Проверено ${batch.done} из ${batch.total} примеров`
              : `${visible.length} из ${items.length} примеров · локальная обработка`}
          </span>
          <div className="fixture-footer-actions">
            <button
              className={"button " + (view === "batch" ? "primary" : "")}
              disabled={loading || busy || !items.length || batchRunning}
              title="Проверить все примеры, включая скрытые поиском и фильтрами"
              onClick={launchAll}
            >
              {busy ? (
                <Loader2 size={17} className="spin" />
              ) : (
                <CheckCheck size={17} />
              )}
              {batchRunning
                ? "Проверяем все примеры…"
                : view === "batch"
                  ? "Проверить все примеры снова"
                  : `Проверить все примеры (${items.length})`}
            </button>
            {view === "catalog" && (
              <button
                className="button primary"
                disabled={loading || busy || !active}
                onClick={launch}
              >
                {busy ? (
                  <Loader2 size={17} className="spin" />
                ) : (
                  <ArrowRight size={17} />
                )}{" "}
                {busy ? "Загружаем комплект…" : "Запустить проверку"}
              </button>
            )}
          </div>
        </footer>
      </section>
    </div>
  );
}

const trainingScope = {
  contract: "24/03/15-01",
  stage: "3",
  period_start: "2026-01-01",
  period_end: "2026-05-31",
};
type TrainingDocument = { name: string; url: string; last_modified: number };
type TrainingDocumentRole = "report" | "primary";

function NewCaseModal({
  onClose,
  onDone,
  initialTutorial = false,
  training = false,
}: {
  onClose: () => void;
  onDone: (id: string) => void;
  initialTutorial?: boolean;
  training?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [tutorialOpen, setTutorialOpen] = useState(initialTutorial);
  const [trainingStep, setTrainingStep] = useState(0);
  const [completePackage, setCompletePackage] = useState(false);
  const [reportFiles, setReportFiles] = useState<File[]>([]);
  const [primaryFiles, setPrimaryFiles] = useState<File[]>([]);
  const [trainingLoad, setTrainingLoad] = useState<TrainingDocumentRole | null>(null);
  const [trainingFileError, setTrainingFileError] = useState<{ role: TrainingDocumentRole; message: string } | null>(null);
  const trainingRequest = useRef<AbortController | null>(null);
  useEffect(() => () => {
    trainingRequest.current?.abort();
    trainingRequest.current = null;
  }, []);
  const reportContext = useReportContext();
  const reportInput = useRef<HTMLInputElement>(null);
  const primaryInput = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const attempt = useRef<{ id: string; signature: string } | null>(null);
  const dialog = useDialog(onClose, busy);
  const validFile = (file: File, report: boolean) => !!file.size && file.size <= 25 * 1024 * 1024 &&
    (report ? /\.(pdf|png|jpe?g)$/i : /\.(pdf|docx|xlsx|png|jpe?g)$/i).test(file.name);
  const reportReady = reportFiles.length === 1 && validFile(reportFiles[0], true);
  const scopeReady = reportContext.values.contract.trim() === trainingScope.contract &&
    Number(reportContext.values.stage) === Number(trainingScope.stage) &&
    reportContext.values.period_start === trainingScope.period_start &&
    reportContext.values.period_end === trainingScope.period_end;
  const primaryReady = primaryFiles.length === 22 && primaryFiles.every((file) => validFile(file, false));
  const preparationReady = reportReady && scopeReady && primaryReady && completePackage;
  const fillTrainingDocuments = async (role: TrainingDocumentRole) => {
    if (!training || busy || trainingRequest.current) return;
    const request = new AbortController();
    trainingRequest.current = request;
    setTrainingLoad(role);
    setTrainingFileError(null);
    try {
      const documents = await api<TrainingDocument[]>(`/demo/documents?role=${role}`, { signal: request.signal });
      const files = await Promise.all(documents.map(async (document) => {
        const response = await fetch(document.url, { signal: request.signal });
        if (!response.ok) throw new Error("Не удалось получить учебный документ.");
        const blob = await response.blob();
        return new File([blob], document.name, { type: blob.type, lastModified: document.last_modified });
      }));
      if (request.signal.aborted) return;
      if (files.length !== (role === "report" ? 1 : 22) || files.some((file) => !validFile(file, role === "report"))) {
        throw new Error("Учебный комплект неполон или содержит неподдерживаемый файл.");
      }
      if (role === "report") {
        setReportFiles(files);
        if (reportInput.current) reportInput.current.value = "";
        void reportContext.inspect(files[0]);
      } else {
        setPrimaryFiles(files);
        if (primaryInput.current) primaryInput.current.value = "";
      }
      setError("");
    } catch {
      if (!request.signal.aborted) {
        setTrainingFileError({ role, message: "Не удалось добавить учебные документы. Повторите попытку или выберите файлы вручную." });
        request.abort();
      }
    } finally {
      if (trainingRequest.current === request) {
        trainingRequest.current = null;
        setTrainingLoad(null);
      }
    }
  };
  const trainingDocumentButton = (role: TrainingDocumentRole) => <>
    <button type="button" className="button tutorial-fill-button" disabled={busy || trainingLoad !== null}
      onClick={() => void fillTrainingDocuments(role)}>
      {trainingLoad === role ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
      {trainingLoad === role ? "Добавляем документы…" : role === "report" ? "Подставить КФЗ примера" : "Подставить документы примера"}
    </button>
    {trainingFileError?.role === role && <p className="tutorial-file-error" role="alert">{trainingFileError.message}</p>}
  </>;
  const fillTrainingScope = () => {
    if (!training || busy) return;
    reportContext.change("contract", trainingScope.contract);
    reportContext.change("stage", trainingScope.stage);
    reportContext.change("period_start", trainingScope.period_start);
    reportContext.change("period_end", trainingScope.period_end);
  };
  const trainingSteps: TutorialStep[] = [
    { target: "report", anchor: "report", title: "Выберите учебный КФЗ", text: "Подставьте готовый КФЗ кнопкой ниже или скачайте архив и выберите PDF из папки report вручную.",
      content: <>{trainingDocumentButton("report")}<a className="button tutorial-kit-link" href="/api/demo/documents.zip"><ArrowDownToLine size={16} />Скачать учебный архив</a></>,
      complete: reportReady && trainingLoad !== "report", waitingText: trainingLoad === "report" ? "Подготавливаем учебный КФЗ…" : "Выберите один непустой PDF, PNG или JPEG до 25 МБ.", successText: "КФЗ выбран. Проверьте файл и нажмите «Далее»." },
    { target: "scope", anchor: "scope", title: "Проверьте параметры примера", text: "Заполним договор, этап и период учебной проверки. Значения можно изменить.",
      content: <>
        <button type="button" className="button tutorial-fill-button" disabled={busy}
          aria-describedby="tutorial-description" onClick={fillTrainingScope}>
          <Sparkles size={16} />Подставить данные примера
        </button>
      </>,
      complete: scopeReady, waitingText: "Укажите договор 24/03/15-01, этап 3 и период с 01.01.2026 по 31.05.2026.",
      successText: "Параметры заполнены. Проверьте значения и нажмите «Далее»." },
    { target: "primary", anchor: "primary", title: "Выберите первичные документы", text: "Подставьте все 22 документа кнопкой ниже или выберите их вручную из папки primary распакованного учебного архива.",
      content: trainingDocumentButton("primary"),
      complete: primaryReady && trainingLoad !== "primary", waitingText: trainingLoad === "primary" ? "Подготавливаем учебные документы…" : `Выбрано ${primaryFiles.length} из 22 документов. Нужны непустые файлы поддерживаемых форматов до 25 МБ каждый.`, successText: "Все 22 документа выбраны. Проверьте список и нажмите «Далее»." },
    { target: "complete", title: "Подтвердите полноту комплекта", text: "В учебном комплекте представлены все первичные документы за выбранный период. Отметьте это, чтобы сверка могла сделать вывод о полной сумме расходов.",
      complete: completePackage, waitingText: "Поставьте галочку «Все первичные документы за период загружены».", successText: "Комплект отмечен как полный." },
    { target: "submit", title: "Запустите учебную сверку", text: "Документы и параметры готовы. Нажмите «Начать сверку»: файлы загрузятся, после обработки продолжим обучение на результатах.",
      complete: preparationReady && !busy, waitingText: error || (busy ? progress : "Вернитесь назад и проверьте документы, параметры и полноту комплекта."), successText: "Всё готово к запуску." },
  ];
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (busy || trainingLoad || (training && (trainingStep !== 4 || !preparationReady))) return;
    const form = new FormData(e.currentTarget);
    setError("");
    const allowedReport = /\.(pdf|png|jpe?g)$/i;
    const allowedPrimary = /\.(pdf|docx|xlsx|png|jpe?g)$/i;
    const files = [...reportFiles, ...primaryFiles];
    if (reportFiles.length !== 1 || !primaryFiles.length) {
      setError("Выберите один отчёт и хотя бы один первичный документ.");
      return;
    }
    if (files.length > 100) {
      setError(
        "В одной проверке можно загрузить до 100 файлов, включая отчёт.",
      );
      return;
    }
    const invalid = files.find(
      (f) =>
        !f.size ||
        f.size > 25 * 1024 * 1024 ||
        !(reportFiles.includes(f) ? allowedReport : allowedPrimary).test(
          f.name,
        ),
    );
    if (invalid) {
      setError(
        `Файл «${invalid.name}»: проверьте формат и размер. Нужен непустой документ до 25 МБ.`,
      );
      return;
    }
    const start = String(form.get("start")),
      end = String(form.get("end"));
    if (end < start) {
      setError("Конец периода должен быть не раньше начала.");
      return;
    }
    if (start.slice(0, 4) !== end.slice(0, 4)) {
      setError(
        "Выберите период в пределах одного года: сверка проверяет одну годовую строку КФЗ.",
      );
      return;
    }
    const context = {
      title: form.get("title"),
      contract: String(form.get("contract")).trim(),
      stage: Number(form.get("stage")),
      period_start: start,
      period_end: end,
      complete_package: form.get("complete") === "on",
    };
    if (!context.contract) {
      setError("Укажите номер договора из отчёта.");
      return;
    }
    const signature = JSON.stringify([
      context,
      files.map((file) => [file.name, file.size, file.lastModified]),
    ]);
    reportContext.stop();
    setTutorialOpen(false);
    setBusy(true);
    try {
      setProgress("Создаём проверку…");
      if (attempt.current?.signature !== signature) {
        const created = await api<Case>("/cases", json(context));
        attempt.current = { id: created.id, signature };
      }
      const caseId = attempt.current!.id;
      // Reuse the draft after a failed request, including a lost upload response.
      const draft = await api<Case>(`/cases/${caseId}`);
      if (
        draft.status === "queued" ||
        draft.status === "running" ||
        draft.status === "completed"
      ) {
        onDone(caseId);
        return;
      }
      for (const [role, selectedFiles] of [
        ["report", reportFiles],
        ["primary", primaryFiles],
      ] as const) {
        if (
          draft.documents?.filter((d) => d.role === role).length ===
          selectedFiles.length
        )
          continue;
        setProgress(
          role === "report"
            ? "Загружаем отчёт…"
            : `Загружаем первичные документы: ${selectedFiles.length}…`,
        );
        const body = new FormData();
        body.set("role", role);
        selectedFiles.forEach((file) => body.append("files", file));
        await api(`/cases/${caseId}/documents`, { method: "POST", body });
      }
      setProgress("Запускаем сверку…");
      await api(`/cases/${caseId}/runs`, { method: "POST" });
      onDone(caseId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setProgress("");
    }
  };
  return (
    <div className="overlay">
      <section
        className="modal new-case-modal"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label={training ? "Учебная проверка" : "Новая проверка"}
      >
        <header className="new-case-heading">
          <span className="eyebrow">{training ? "ПРАКТИКА С ПОДСКАЗКАМИ" : "СВЕРКА ПО ВАШИМ ДОКУМЕНТАМ"}</span>
          <h2>{training ? "Проверим учебный комплект" : "Новая проверка"}</h2>
          <p>{training ? "Выберите КФЗ и 22 первичных документа из учебного архива. Каждый шаг откроется после выполнения предыдущего." : "Добавьте документы и укажите, какую строку отчёта проверить."}</p>
          {!training && <button type="button" className="tutorial-start" data-tutorial-start
            disabled={busy} onClick={() => setTutorialOpen(true)}>
            <CircleHelp size={16} />Показать подсказки
          </button>}
          <button
            className="close"
            disabled={busy}
            aria-label="Закрыть"
            onClick={onClose}
          >
            <X />
          </button>
        </header>
        <form ref={formRef} onSubmit={submit} className="new-case-form">
          <div className="new-case-fields">
            <fieldset disabled={busy || trainingLoad !== null}>
              <legend>
                <span>1</span>Документы
              </legend>
              <div className="upload-grid">
                <div data-tutorial="report">
                  <label
                    className={
                      "file-input " + (reportFiles.length ? "selected" : "")
                    }
                  >
                    <FileText size={23} />
                    <span>
                      <strong>
                        {reportFiles[0]?.name || "Выберите отчёт КФЗ"}
                      </strong>
                      <small>Один PDF, PNG или JPEG · до 25 МБ</small>
                    </span>
                    <input
                      ref={reportInput}
                      aria-label="Итоговый отчёт КФЗ"
                      name="report"
                      type="file"
                      required={!reportFiles.length}
                      accept=".pdf,.png,.jpg,.jpeg"
                      onChange={(e) => {
                        const selected = Array.from(e.target.files || []);
                        setReportFiles(selected);
                        void reportContext.inspect(selected[0]);
                        setTrainingFileError(null);
                        setError("");
                      }}
                    />
                  </label>
                  {!!reportFiles.length && (
                    <button
                      type="button"
                      className="text-button remove-files"
                      onClick={() => {
                        setReportFiles([]);
                        void reportContext.inspect();
                        setTrainingFileError(null);
                        if (reportInput.current) reportInput.current.value = "";
                      }}
                    >
                      Убрать отчёт
                    </button>
                  )}
                </div>
                <div data-tutorial="primary">
                  <label
                    className={
                      "file-input " + (primaryFiles.length ? "selected" : "")
                    }
                  >
                    <Files size={23} />
                    <span>
                      <strong>
                        {primaryFiles.length
                          ? `Выбрано документов: ${primaryFiles.length}`
                          : "Выберите первичные документы"}
                      </strong>
                      <small>
                        PDF, DOCX, XLSX, PNG, JPEG · до 25 МБ каждый
                      </small>
                    </span>
                    <input
                      ref={primaryInput}
                      aria-label="Первичные документы"
                      name="primary"
                      type="file"
                      required={!primaryFiles.length}
                      multiple
                      accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg"
                      onChange={(e) => {
                        setPrimaryFiles(Array.from(e.target.files || []));
                        setTrainingFileError(null);
                        setError("");
                      }}
                    />
                  </label>
                  {!!primaryFiles.length && (
                    <>
                      <p
                        className="selected-files"
                        title={primaryFiles.map((file) => file.name).join("\n")}
                      >
                        {primaryFiles
                          .slice(0, 3)
                          .map((file) => file.name)
                          .join(", ")}
                        {primaryFiles.length > 3
                          ? ` и ещё ${primaryFiles.length - 3}`
                          : ""}
                      </p>
                      <button
                        type="button"
                        className="text-button remove-files"
                        onClick={() => {
                          setPrimaryFiles([]);
                          setTrainingFileError(null);
                          if (primaryInput.current)
                            primaryInput.current.value = "";
                        }}
                      >
                        Убрать документы
                      </button>
                    </>
                  )}
                </div>
              </div>
            </fieldset>
            <fieldset disabled={busy}>
              <legend>
                <span>2</span>Область сверки
              </legend>
              <p className="form-help" id="scope-help">
                Договор исключает чужие документы, этап выбирает строку КФЗ,
                даты ограничивают период расходов. Найденные параметры можно
                исправить; пустые поля заполните вручную.
              </p>
              <p className="context-recognition" role="status" aria-live="polite">
                {reportContext.loading && <Loader2 size={16} className="spin" />}
                {reportContext.loading
                  ? "Распознаём параметры КФЗ… Можно заполнять поля вручную."
                  : reportContext.error || (reportContext.recognized
                    ? "Проверьте найденные значения перед запуском сверки."
                    : "После загрузки КФЗ попробуем заполнить параметры автоматически.")}
              </p>
              <label className="form-field">
                Название проверки
                <input
                  name="title"
                  required
                  defaultValue={training ? "Учебная сверка · этап 3" : "Сверка затрат"}
                  maxLength={200}
                />
              </label>
              <div className="form-grid" data-tutorial="scope">
                <label>
                  Номер договора
                  <input
                    name="contract"
                    required
                    placeholder="Например, 24/03/15-01"
                    maxLength={80}
                    aria-describedby="scope-help"
                    value={reportContext.values.contract}
                    onChange={(e) => reportContext.change("contract", e.target.value)}
                  />
                  <small className="context-field-hint">{reportContext.hint("contract")}</small>
                </label>
                <label>
                  Этап
                  <input
                    name="stage"
                    required
                    type="number"
                    min="1"
                    max="100"
                    placeholder="Номер из отчёта"
                    value={reportContext.values.stage}
                    onChange={(e) => reportContext.change("stage", e.target.value)}
                  />
                  <small className="context-field-hint">{reportContext.hint("stage")}</small>
                </label>
                <label>
                  Начало периода
                  <DateInput
                    name="start"
                    label="Начало периода"
                    required
                    value={reportContext.values.period_start}
                    onChange={(value) => reportContext.change("period_start", value)}
                  />
                  <small className="context-field-hint">{reportContext.hint("period_start")}</small>
                </label>
                <label>
                  Конец периода
                  <DateInput
                    name="end"
                    label="Конец периода"
                    required
                    min={reportContext.values.period_start || undefined}
                    value={reportContext.values.period_end}
                    onChange={(value) => reportContext.change("period_end", value)}
                  />
                  <small className="context-field-hint">{reportContext.hint("period_end")}</small>
                </label>
              </div>
              <label className="checkbox" data-tutorial="complete">
                <input name="complete" type="checkbox" checked={completePackage} onChange={(e) => setCompletePackage(e.target.checked)} />
                <span>
                  Все первичные документы за период загружены
                  <small>
                    Отметьте для полного комплекта. При частичной загрузке вывод
                    будет ограничен подтверждёнными расходами.
                  </small>
                </span>
              </label>
            </fieldset>
          </div>
          <div className="new-case-footer">
            {error && (
              <p role="alert" className="form-error">
                <CircleAlert size={17} />
                {error}
              </p>
            )}
            <span role="status">
              {busy
                ? progress
                : `${reportFiles.length ? "Отчёт выбран" : "Отчёт не выбран"} · Первичных документов: ${primaryFiles.length}`}
            </span>
            <button className="button primary" type="submit" disabled={busy || (training && (trainingStep !== 4 || !preparationReady))} data-tutorial="submit">
              {busy ? (
                <Loader2 size={18} className="spin" />
              ) : (
                <ShieldCheck size={18} />
              )}
              {busy ? "Подготавливаем…" : "Начать сверку"}
            </button>
          </div>
        </form>
        {tutorialOpen && <CheckTutorial root={dialog} onClose={() => setTutorialOpen(false)} />}
        {training && <CheckTutorial root={dialog} steps={trainingSteps} step={trainingStep} totalSteps={11}
          label="Учебный пример" exitLabel="Выйти" finishLabel="Начать сверку"
          onClose={() => { if (!busy) onClose(); }}
          onStepChange={(next) => {
            if (!busy && (next < trainingStep || trainingSteps[trainingStep].complete)) setTrainingStep(next);
          }}
          onFinish={() => formRef.current?.requestSubmit()} />}
      </section>
    </div>
  );
}

function SourcePanel({
  source,
  caseId,
  focusEvidence,
  onClose,
  onReviewed,
}: {
  source: { doc: Doc; evidence?: Evidence };
  caseId: string;
  focusEvidence: boolean;
  onClose: () => void;
  onReviewed: () => Promise<void>;
}) {
  const { doc, evidence: ev } = source;
  const [editing, setEditing] = useState(false),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [imageError, setImageError] = useState(false);
  const dialog = useDialog(onClose, saving);
  const image = /\.(pdf|png|jpe?g)$/i.test(doc.name);
  const matchesEvidence = (fragment: Evidence) => !!(
    (ev?.range && fragment.sheet === ev.sheet && rangeContains(ev.range, fragment.range || "")) ||
    (ev?.table && fragment.table === ev.table && fragment.row === ev.row && fragment.column === ev.column) ||
    (ev?.paragraph && fragment.paragraph === ev.paragraph));
  const highlightedFragment = doc.extraction?.fragments?.findIndex(matchesEvidence) ?? -1;
  const hasVisualEvidence = image ? !!ev?.bbox && !imageError : highlightedFragment >= 0;
  const review = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setSaving(true);
    setError("");
    try {
      await api(
        `/cases/${caseId}/documents/${doc.id}/review`,
        json({
          article: form.get("article"),
          amount: form.get("amount"),
          reason: form.get("reason"),
        }),
      );
      await onReviewed();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  const loc = ev?.sheet
    ? `${ev.sheet}!${ev.range}`
    : ev?.page
      ? `Страница ${ev.page}`
      : ev?.table
        ? `Таблица ${ev.table}, строка ${ev.row}, колонка ${ev.column}`
        : ev?.paragraph
          ? `Абзац ${ev.paragraph}`
          : "Документ";
  return (
    <div className="overlay source-overlay" onClick={onClose}>
      <section
        className="source-panel"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label="Первичный документ"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="source-heading">
          <button className="text-button" onClick={onClose}>
            <ArrowLeft size={17} />К результатам
          </button>
          <button
            className="icon-button"
            aria-label="Закрыть документ"
            onClick={onClose}
          >
            <X />
          </button>
        </div>
        <div className="source-title">
          <FileText size={22} />
          <div>
            <h2>{doc.name}</h2>
            <p>{loc}</p>
          </div>
          <a
            className="button"
            href={`/api/cases/${caseId}/documents/${doc.id}/original`}
          >
            <ArrowDownToLine size={16} />
            Оригинал
          </a>
        </div>
        <div className="source-body">
          <div className={"source-preview " + (image && !imageError ? "source-preview-image" : "")}>
            {image ? (
              imageError ? (
                <p className="notice">
                  Предпросмотр недоступен. Скачайте оригинал.
                </p>
              ) : (
                <DocumentImagePreview key={`${doc.id}:${ev?.page || 1}`} bbox={ev?.bbox}
                  evidenceText={ev?.text} amount={doc.extraction?.amount}
                  focusInitially={focusEvidence} onError={() => setImageError(true)}
                  alt={doc.role === "report" ? "Страница отчёта КФЗ" : "Страница первичного документа"}
                  src={`/api/cases/${caseId}/documents/${doc.id}/page/${ev?.page || 1}?dpi=300`} />
              )
            ) : (
              <div className="structured-document">
                <span className="eyebrow">СОДЕРЖИМОЕ ДОКУМЕНТА</span>
                {doc.extraction?.fragments?.map((f, i) => (
                  <div
                    key={i}
                    className={"fragment " + (matchesEvidence(f) ? "highlight" : "")}
                    data-tutorial={i === highlightedFragment ? "example-evidence" : undefined}
                  >
                    <small>
                      {f.sheet
                        ? `${f.sheet}!${f.range}`
                        : f.table
                          ? `Таблица ${f.table} · ${f.row}:${f.column}`
                          : `Абзац ${f.paragraph}`}
                    </small>
                    <p>{f.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
          <aside className="source-facts">
            <h3>Подтверждающий фрагмент</h3>
            {ev ? (
              <blockquote data-tutorial={!hasVisualEvidence ? "example-evidence" : undefined}>{ev.text}</blockquote>
            ) : (
              <p className="muted">
                Выберите слагаемое в расчёте для перехода к конкретному
                фрагменту.
              </p>
            )}
            <dl>
              <dt>Договор</dt>
              <dd>{doc.extraction?.contract || "Не извлечён"}</dd>
              <dt>Номер документа</dt>
              <dd>{doc.extraction?.number || "Не извлечён"}</dd>
              <dt>Период операции</dt>
              <dd>
                {doc.extraction?.period_start
                  ? `${dt(doc.extraction.period_start)} — ${dt(doc.extraction.period_end || doc.extraction.period_start)}`
                  : "Не извлечён"}
              </dd>
              <dt>Сумма</dt>
              <dd>{rub(doc.extraction?.amount)} ₽</dd>
              <dt>Статья</dt>
              <dd>
                {doc.extraction?.article
                  ? `${doc.extraction.article} · ${articles[doc.extraction.article]}`
                  : "Не определена"}
              </dd>
            </dl>
            {doc.extraction?.classification_evidence && (
              <>
                <h3>Основание классификации</h3>
                <p className="classification-text">
                  {doc.extraction.classification_evidence.text}
                </p>
              </>
            )}
            {doc.error && <p className="notice">{doc.error}</p>}
            {doc.role === "primary" && doc.extraction && !doc.error && (
              <>
                <button
                  className="button full"
                  onClick={() => setEditing(!editing)}
                >
                  <SlidersHorizontal size={16} />
                  Уточнить данные
                </button>
                {editing && (
                  <form className="review-form" onSubmit={review}>
                    <label>
                      Статья
                      <select
                        name="article"
                        defaultValue={doc.extraction.article}
                      >
                        {Object.entries(articles).map(([k, v]) => (
                          <option value={k} key={k}>
                            {k} · {v}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Сумма, ₽
                      <input
                        name="amount"
                        required
                        defaultValue={doc.extraction.amount}
                        inputMode="decimal"
                      />
                    </label>
                    <label>
                      Причина уточнения
                      <textarea
                        name="reason"
                        minLength={5}
                        required
                        placeholder="Укажите основание изменения"
                      />
                    </label>
                    {error && <p className="form-error">{error}</p>}
                    <button className="button primary full" disabled={saving}>
                      {saving ? (
                        <Loader2 size={16} className="spin" />
                      ) : (
                        <Check size={16} />
                      )}
                      Сохранить и пересчитать
                    </button>
                    <small>
                      Исходное извлечение и предыдущий результат сохраняются в
                      истории.
                    </small>
                  </form>
                )}
              </>
            )}
          </aside>
        </div>
      </section>
    </div>
  );
}
function rangeContains(range: string, cell: string) {
  const points = range.split(":");
  if (points.length === 1) return range === cell;
  const col = (s: string) => s.replace(/\d/g, "");
  return (
    col(points[0]) === col(cell) &&
    Number(cell.replace(/\D/g, "")) >= Number(points[0].replace(/\D/g, "")) &&
    Number(cell.replace(/\D/g, "")) <= Number(points[1].replace(/\D/g, ""))
  );
}
createRoot(document.getElementById("root")!).render(<App />);
