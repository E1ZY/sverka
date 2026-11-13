export function CaseId({ id, compact = false }: { id: string; compact?: boolean }) {
  return <span className="case-id" title={`ID проверки: ${id}`}>
    ID: {compact ? id.slice(0, 8) : id}
  </span>;
}
