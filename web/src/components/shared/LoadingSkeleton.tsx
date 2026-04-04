interface Props {
  className?: string;
  count?: number;
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`card px-4 py-4 flex flex-col gap-3 ${className}`}>
      <div className="skeleton h-3 w-20" />
      <div className="skeleton h-7 w-28" />
      <div className="skeleton h-3 w-16" />
    </div>
  );
}

export function SkeletonChart({ className = '', height = '300px' }: { className?: string; height?: string }) {
  return <div className={`skeleton w-full rounded-xl ${className}`} style={{ height }} />;
}

export default function LoadingSkeleton({ className = '', count = 4 }: Props) {
  return (
    <div className={`grid grid-cols-2 lg:grid-cols-4 gap-3 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
