export type TableSort = { field: string; direction: 'asc' | 'desc' };

export function SortHeader({
  label,
  field,
  sort,
  onSort,
  numeric = false,
}: {
  label: string;
  field: string;
  sort: TableSort;
  onSort: (value: TableSort) => void;
  numeric?: boolean;
}) {
  const active = sort.field === field;
  const next = active && sort.direction === 'asc' ? 'desc' : 'asc';
  return (
    <th
      scope="col"
      className={numeric ? 'numeric' : undefined}
      aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        className="sort-button"
        aria-label={`Ordina ${label.toLowerCase()} in ordine ${next === 'asc' ? 'crescente' : 'decrescente'}`}
        onClick={() => onSort({ field, direction: next })}
      >
        {label}
        <span aria-hidden="true">{active ? (sort.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
      </button>
    </th>
  );
}
