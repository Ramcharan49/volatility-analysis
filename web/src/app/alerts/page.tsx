export default function AlertsPage() {
  return (
    <div className="max-w-7xl mx-auto px-6 py-6 flex items-center justify-center min-h-[60vh]">
      <div
        className="card px-8 py-10 text-center flex flex-col items-center gap-4 max-w-md animate-in stagger-1"
      >
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center"
          style={{ background: 'var(--accent-cyan-dim)', color: 'var(--accent-cyan)' }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          Alerts Coming Soon
        </h2>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          Configure alerts for regime changes, percentile breaches, and flow spikes.
          Get notified in-app and via email when the vol surface moves.
        </p>
        <div className="flex items-center gap-2 mt-2">
          <span
            className="text-xs px-2.5 py-1 rounded-full"
            style={{ background: 'var(--accent-cyan-dim)', color: 'var(--accent-cyan)' }}
          >
            V2
          </span>
          <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
            Alert rules, cooldowns, email delivery
          </span>
        </div>
      </div>
    </div>
  );
}
