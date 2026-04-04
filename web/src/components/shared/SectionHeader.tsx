interface Props {
  title: string;
  subtitle?: string;
}

export default function SectionHeader({ title, subtitle }: Props) {
  return (
    <div className="flex items-baseline gap-3 mb-4 mt-2">
      <h3 className="section-header">{title}</h3>
      {subtitle && (
        <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
          {subtitle}
        </span>
      )}
    </div>
  );
}
