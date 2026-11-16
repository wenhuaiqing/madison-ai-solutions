// The workbench's mark: three lines of a document, matched and ticked.
// Inline so it takes a colour.
export default function Mark({ colour = "currentColor", size = 24 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
      <path d="M5 9h9M5 16h9M5 23h9" stroke={colour} strokeWidth="3" strokeLinecap="round" />
      <path d="M18 16l3.5 3.5L28 11" stroke="#3FB6A8" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
