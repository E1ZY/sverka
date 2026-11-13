import { useState } from "react";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";

type Evidence = {
  text: string;
  page?: number;
  bbox?: number[];
  sheet?: string;
  range?: string;
  confidence?: number;
};
type Source = {
  document_id: string;
  name: string;
  amount: string;
  evidence?: Evidence;
};
type TreeNode = {
  id: string;
  name: string;
  code?: string;
  actual: string | null;
  expected: string | null;
  delta?: string | null;
  status: string;
  confirmed_subtotal?: string | null;
  allocation?: boolean;
  children: TreeNode[];
  sources: Source[];
  reason?: string;
  reference?: boolean;
  evidence?: Evidence;
  report_id?: string;
};
type Metadata = Record<
  string,
  { label: string; value: string | null; status: string; evidence?: Evidence }
>;
type Validation = {
  id: string;
  name: string;
  role: string;
  article: string | null;
  period: string;
  amount: string | null;
  accepted: boolean;
  verdict: string;
  reason: string;
  metadata: Metadata;
  checks: {
    field: string;
    value: string | null;
    expected: string | null;
    status: string;
  }[];
};
export type TreeSnapshot = {
  root: TreeNode;
  metadata: Metadata;
  note: string;
  document_validation: Validation[];
};
const rub = (value: string | null | undefined) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("ru-RU", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(Number(value));
const labels: Record<string, string> = {
  MATCH: "Обосновано",
  MISMATCH: "Расхождение",
  INSUFFICIENT_DATA: "Не обосновано",
  REFERENCE: "Справочно",
  UNALLOCATED: "Не распределено",
};
const groups: Record<string, string> = {
  "0200": "Оплата труда",
  "0300": "Страховые взносы",
  "0800": "Общепроизводственные затраты",
  "0900": "Общехозяйственные затраты",
  unknown: "Статья не определена",
};

function MetadataTable({
  metadata,
  onSource,
  reportId,
}: {
  metadata: Metadata;
  onSource: (id: string, evidence?: Evidence) => void;
  reportId?: string;
}) {
  return (
    <table className="register-table metadata-table">
      <thead>
        <tr>
          <th>Поле</th>
          <th>Значение из карточки</th>
          <th>Источник</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(metadata).map(([key, item]) => (
          <tr key={key}>
            <td>{item.label}</td>
            <td>
              {item.value || (
                <span className="subtle">
                  {item.status === "ambiguous"
                    ? "Найдено несколько значений"
                    : "Не найдено в документе"}
                </span>
              )}
              {item.status === "uncertain" && (
                <small className="metadata-uncertain">
                  Проверьте распознавание
                </small>
              )}
            </td>
            <td>
              {item.value && item.evidence && reportId && (
                <button
                  className="text-button"
                  onClick={() => onSource(reportId, item.evidence)}
                >
                  <FileText size={14} />
                  Страница {item.evidence.page || 1}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DocumentsTree({
  items,
  onSource,
}: {
  items: Validation[];
  onSource: (id: string, evidence?: Evidence) => void;
}) {
  const [closed, setClosed] = useState(new Set<string>());
  const [selected, setSelected] = useState<Validation | null>(null);
  const [verdict, setVerdict] = useState("all");
  const primary = items.filter(item => item.role === "primary");
  const acceptedCount = primary.filter(item => item.accepted).length;
  const toggle = (id: string) =>
    setClosed((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const grouped = new Map<string, Map<string, Validation[]>>();
  for (const item of primary.filter(item => verdict === "all" || item.accepted === (verdict === "accepted"))) {
    const category = item.article || "unknown";
    if (!grouped.has(category)) grouped.set(category, new Map());
    const periods = grouped.get(category)!;
    periods.set(item.period, [...(periods.get(item.period) || []), item]);
  }
  return (
    <>
      <p className="tree-explanation">
        Все входящие документы остаются в дереве. В расчёт включаются только
        принятые документы. Суммы отклонённых документов в итог не входят.
      </p>
      <div className="register-toolbar"><div className="filters" aria-label="Решение по документам">{[["all", `Все (${primary.length})`], ["accepted", `Принято (${acceptedCount})`], ["rejected", `Отклонено (${primary.length-acceptedCount})`]].map(([key,label])=><button key={key} className={verdict===key?"active":""} aria-pressed={verdict===key} onClick={()=>{setVerdict(key); setSelected(null);}}>{label}</button>)}</div></div>
      <div className="register-scroll">
        <table className="register-table intake-tree">
          <thead>
            <tr>
              <th>Отчётные документы</th>
              <th>Сумма, ₽</th>
              <th>Проверенные признаки</th>
              <th>Решение и причина</th>
            </tr>
          </thead>
          <tbody>
            {[...grouped].map(([code, periods]) => {
              const docs = [...periods.values()].flat(),
                rejected = docs.filter((item) => !item.accepted).length;
              return (
                <TreeGroup
                  key={code}
                  code={code}
                  periods={periods}
                  rejected={rejected}
                  closed={closed}
                  toggle={toggle}
                  onSelect={setSelected}
                  onSource={onSource}
                />
              );
            })}
          </tbody>
        </table>
      </div>
      {selected && (
        <section className="metadata-detail">
          <div className="panel-heading">
            <h3>{selected.name}</h3>
            <button className="text-button" onClick={() => setSelected(null)}>
              Скрыть признаки
            </button>
          </div>
          <table className="register-table">
            <thead>
              <tr>
                <th>Признак</th>
                <th>В документе</th>
                <th>В главном отчёте / параметрах</th>
                <th>Проверка</th>
              </tr>
            </thead>
            <tbody>
              {selected.checks.map((check) => (
                <tr key={check.field}>
                  <td>{check.field}</td>
                  <td>{check.value || "Не найдено"}</td>
                  <td>{check.expected || "Не найдено"}</td>
                  <td>
                    {check.status === "MATCH"
                      ? "Совпадает"
                      : check.status === "MISSING"
                        ? "Недостаточно данных"
                        : check.status === "NOT_COMPARABLE"
                          ? "Иная роль в операции — нужно сопоставление сторон"
                          : check.status === "EXTRACTED" ? "Извлечено из документа"
                          : check.status === "UNCERTAIN" ? "Проверьте распознавание"
                          : "Не соответствует"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <MetadataTable
            metadata={selected.metadata}
            reportId={selected.id}
            onSource={onSource}
          />
        </section>
      )}
    </>
  );
}

function TreeGroup({
  code,
  periods,
  rejected,
  closed,
  toggle,
  onSelect,
  onSource,
}: {
  code: string;
  periods: Map<string, Validation[]>;
  rejected: number;
  closed: Set<string>;
  toggle: (id: string) => void;
  onSelect: (value: Validation) => void;
  onSource: (id: string) => void;
}) {
  return (
    <>
      <tr className={"intake-group " + (rejected ? "rejected" : "accepted")}>
        <td colSpan={3}>
          <button
            className="tree-toggle"
            aria-expanded={!closed.has(code)}
            onClick={() => toggle(code)}
          >
            {closed.has(code) ? (
              <ChevronRight size={16} />
            ) : (
              <ChevronDown size={16} />
            )}
            <strong>{groups[code] || code}</strong>
          </button>
        </td>
        <td>
          {rejected
            ? `Отклонено документов: ${rejected}`
            : "Все документы приняты"}
        </td>
      </tr>
      {!closed.has(code) &&
        [...periods].sort(([left], [right])=>left.localeCompare(right)).map(([period, docs]) => (
          <tr key={period}>
            <td colSpan={4} className="intake-period-cell">
              <details open>
                <summary>{period}</summary>
                <table className="register-table">
                  <tbody>
                    {docs.map((item) => (
                      <tr
                        key={item.id}
                        className={item.accepted ? "accepted" : "rejected"}
                      >
                        <td>
                          <button
                            className="text-button"
                            onClick={() => onSource(item.id)}
                          >
                            {item.name}
                          </button>
                        </td>
                        <td className="money">{rub(item.amount)}</td>
                        <td>
                          <button
                            className="text-button"
                            onClick={() => onSelect(item)}
                          >
                            Признаки проверки
                          </button>
                        </td>
                        <td>
                          <strong>{item.verdict}</strong>
                          <p>{item.reason}</p>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </td>
          </tr>
        ))}
    </>
  );
}

export function CostTreePanel({
  tree,
  onSource,
}: {
  tree: TreeSnapshot;
  onSource: (id: string, evidence?: Evidence) => void;
}) {
  const [tab, setTab] = useState("costs"),
    [view, setView] = useState("compare"),
    [issues, setIssues] = useState(false);
  const [expanded, setExpanded] = useState(
    new Set(["stage", ...tree.root.children.map((child) => child.id)]),
  );
  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const flatten = (
    node: TreeNode,
    level = 0,
  ): { node: TreeNode; level: number }[] => [
    ...(!issues || (node.status !== "MATCH" && node.status !== "REFERENCE")
      ? [{ node, level }]
      : []),
    ...(expanded.has(node.id)
      ? node.children.flatMap((child) => flatten(child, level + 1))
      : []),
  ];
  const report = tree.document_validation.find(
    (item) => item.role === "report",
  );
  const allNodes = (node: TreeNode): string[] => [
    node.id,
    ...node.children.flatMap(allNodes),
  ];
  return (
    <section className="panel cost-tree-panel">
      <div className="tree-tabs" aria-label="Представление результата">
        {[
          ["costs", "Деревья затрат"],
          ["incoming", "Дерево отчётности"],
          ["metadata", "Метаданные карточки"],
          ["log", "Журнал решений"],
        ].map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? "active" : ""}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "costs" && (
        <>
          <div className="register-toolbar">
            <div className="tree-views">
              {[
                ["compare", "Сравнение деревьев"],
                ["claimed", "Заявленные затраты"],
                ["confirmed", "Подтверждённые затраты"],
              ].map(([value, label]) => (
                <button
                  className={view === value ? "active" : ""}
                  key={value}
                  onClick={() => setView(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              className="text-button"
              onClick={() => setExpanded(new Set(allNodes(tree.root)))}
            >
              Развернуть всё
            </button>
            <button
              className="text-button"
              onClick={() => setExpanded(new Set(["stage"]))}
            >
              Свернуть
            </button>
            <label className="tree-issues">
              <input
                type="checkbox"
                checked={issues}
                onChange={(event) => setIssues(event.target.checked)}
              />
              Только проблемы
            </label>
          </div>
          <div className="tree-legend">
            <span className="MATCH">Обосновано · 1</span>
            <span className="MISMATCH">Расхождение · 2</span>
            <span className="INSUFFICIENT_DATA">Не обосновано · 3</span>
            <small>
              Родитель получает самый строгий статус потомков. Справочный этап
              исключён.
            </small>
          </div>
          <div className="register-scroll">
            <table
              className="register-table cost-tree"
              role="treegrid"
              aria-label="Дерево затрат"
            >
              <thead>
                <tr>
                  <th>Этап → категория → подкатегория → период</th>
                  {view !== "confirmed" && <th>Заявлено, ₽</th>}
                  {view !== "claimed" && <th>По документам, ₽</th>}
                  {view === "compare" && <th>Разница, ₽</th>}
                  <th>Обоснованность</th>
                  <th>Подтверждающая запись</th>
                </tr>
              </thead>
              <tbody>
              {flatten(tree.root).filter(({node}) => view !== "claimed" || !node.allocation).map(({ node, level }) => (
                  <tr
                    key={node.id}
                    className={node.status}
                    aria-level={level + 1}
                    aria-expanded={
                      node.children.length ? expanded.has(node.id) : undefined
                    }
                  >
                    <td>
                      <div
                        className="tree-label"
                        style={{ paddingLeft: level * 18 }}
                      >
                        {node.children.length ? (
                          <button
                            className="tree-toggle"
                            aria-label={`${expanded.has(node.id) ? "Свернуть" : "Развернуть"} ${node.name}`}
                            onClick={() => toggle(node.id)}
                          >
                            {expanded.has(node.id) ? (
                              <ChevronDown size={15} />
                            ) : (
                              <ChevronRight size={15} />
                            )}
                          </button>
                        ) : (
                          <span className="tree-leaf-dot" />
                        )}
                        <span>
                          {node.code && <small>{node.code}</small>}
                          {node.name}
                        </span>
                      </div>
                    </td>
                    {view !== "confirmed" && (
                      <td className="money">
                        {node.evidence && node.report_id ? (
                          <button
                            title="Показать сумму в главном отчёте"
                            onClick={() =>
                              onSource(node.report_id!, node.evidence)
                            }
                          >
                            {rub(node.actual)}
                          </button>
                        ) : (
                          rub(node.actual)
                        )}
                      </td>
                    )}
                    {view !== "claimed" && (
                      <td className="money">{rub(node.expected ?? node.confirmed_subtotal)}{node.expected == null && node.confirmed_subtotal != null && <small className="partial-amount">Подтверждено частично</small>}</td>
                    )}
                    {view === "compare" && (
                      <td className="money">{rub(node.delta)}</td>
                    )}
                    <td>
                      <span className="tree-status" title={node.reason}>
                        {labels[node.status]}
                      </span>
                    </td>
                    <td>
                      {node.status !== "INSUFFICIENT_DATA" &&
                        node.sources.map((source) => (
                          <button
                            key={source.document_id}
                            className="tree-source"
                            onClick={() =>
                              onSource(source.document_id, source.evidence)
                            }
                          >
                            {source.name}
                            {source.evidence?.sheet
                              ? ` · ${source.evidence.sheet}!${source.evidence.range}`
                              : ` · стр. ${source.evidence?.page || 1}`}{" "}
                            · {rub(source.amount)} ₽
                          </button>
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tree-explanation">{tree.note}</p>
        </>
      )}
      {tab === "incoming" && (
        <DocumentsTree items={tree.document_validation} onSource={onSource} />
      )}
      {tab === "metadata" && (
        <MetadataTable
          metadata={tree.metadata}
          reportId={report?.id}
          onSource={onSource}
        />
      )}
      {tab === "log" && (
        <div className="register-scroll">
          <table className="register-table">
            <thead>
              <tr>
                <th>Документ</th>
                <th>Период</th>
                <th>Решение</th>
                <th>Основание решения</th>
              </tr>
            </thead>
            <tbody>
              {tree.document_validation.map((item) => (
                <tr
                  key={item.id}
                  className={item.accepted ? "accepted" : "rejected"}
                >
                  <td>
                    <button
                      className="text-button"
                      onClick={() => onSource(item.id)}
                    >
                      {item.name}
                    </button>
                  </td>
                  <td>{item.period}</td>
                  <td>{item.verdict}</td>
                  <td>{item.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
