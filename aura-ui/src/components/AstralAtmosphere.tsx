/** Decorative astrolabe: no simulated metrics or fabricated system telemetry. */
export default function AstralAtmosphere() {
  return <div className="astral-atmosphere" aria-hidden="true">
    <div className="astral-grid" />
    <svg className="astral-astrolabe" viewBox="0 0 1000 1000" fill="none">
      <g className="astral-orbit-outer">
        {[460, 420, 365].map(r => <circle key={r} cx="500" cy="500" r={r} stroke="currentColor" strokeWidth="1" />)}
        {Array.from({ length: 72 }, (_, i) => <path key={i} d={i % 6 === 0 ? "M500 40V64" : "M500 40V49"} transform={`rotate(${i * 5} 500 500)`} stroke="currentColor" strokeWidth={i % 6 === 0 ? 2 : 1} />)}
        <path d="M500 40L960 500 500 960 40 500Z" stroke="currentColor" />
      </g>
      <g className="astral-orbit-inner" stroke="currentColor">
        <circle cx="500" cy="500" r="310" strokeDasharray="100 20 5 20" />
        <path d="M500 130L820 685H180Z M500 870L180 315H820Z" />
        <circle cx="500" cy="500" r="255" strokeDasharray="2 13" />
      </g>
    </svg>
    <div className="astral-particles">{Array.from({ length: 24 }, (_, i) => <i key={i} style={{ left: ((i * 37 + 11) % 97) + "%", top: ((i * 23 + 7) % 91) + "%", animationDelay: -(i % 13) + "s", animationDuration: (12 + i % 9) + "s" }} />)}</div>
    <div className="astral-corner top-left" /><div className="astral-corner top-right" />
    <div className="astral-corner bottom-left" /><div className="astral-corner bottom-right" />
  </div>;
}
