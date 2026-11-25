/** The Signal UI section rule: a thin line each side of a small label. */

export default function Divider({ label: text, style }) {
  return (
    <div className="signal-divider" style={style}>
      <div className="signal-divider-mark signal-divider-mark-left" />
      <div className="signal-divider-bar" />
      <span className="signal-divider-label">{text}</span>
      <div className="signal-divider-bar" />
      <div className="signal-divider-mark signal-divider-mark-right" />
    </div>
  );
}
