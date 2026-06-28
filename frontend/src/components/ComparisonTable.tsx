"use client";

interface ComparisonTableProps {
  headers: string[];
  rows: string[][];
}

export function ComparisonTable({ headers, rows }: ComparisonTableProps) {
  return (
    <div className="overflow-x-auto">
      <table
        className="w-full text-sm"
        style={{
          borderCollapse: "separate",
          borderSpacing: 0,
          fontFamily: "var(--font-prose)",
          lineHeight: "var(--leading-ui)",
        }}
      >
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th
                key={i}
                className="px-4 py-2 text-left font-medium text-xs uppercase"
                style={{
                  borderBottom: "2px solid var(--color-primary)",
                  color: "var(--color-primary)",
                  letterSpacing: "var(--tracking-wide)",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td
                  key={j}
                  className="px-4 py-2"
                  style={{
                    borderBottom: "1px solid var(--color-border)",
                    color: j === 0 ? "var(--color-ink)" : "var(--color-muted)",
                    fontWeight: j === 0 ? 500 : 400,
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
