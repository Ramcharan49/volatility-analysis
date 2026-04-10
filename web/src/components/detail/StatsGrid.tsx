'use client';

interface StatItem {
  label: string;
  value: string;
  color?: string;
}

interface Props {
  items: StatItem[];
}

export default function StatsGrid({ items }: Props) {
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {items.map((item) => (
        <div
          key={item.label}
          className="card-dense"
          style={{ padding: '8px 10px' }}
        >
          <div
            className="text-[8px] uppercase"
            style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-label)', letterSpacing: '0.5px' }}
          >
            {item.label}
          </div>
          <div
            className="mono-value font-semibold mt-0.5"
            style={{ fontSize: 15, color: item.color ?? 'var(--text-primary)' }}
          >
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}
