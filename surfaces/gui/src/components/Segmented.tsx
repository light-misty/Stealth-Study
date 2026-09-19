import { useLayoutEffect, useRef, type ReactNode } from "react";

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  testId,
  className,
}: {
  value: T;
  onChange: (next: T) => void;
  options: { value: T; label: ReactNode; testId?: string }[];
  ariaLabel: string;
  testId?: string;
  className?: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const thumbRef = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const track = trackRef.current;
    const thumb = thumbRef.current;
    if (!track || !thumb) return;
    const active = track.querySelector<HTMLButtonElement>("button.active");
    if (!active) return;
    thumb.style.width = `${active.offsetWidth}px`;
    thumb.style.transform = `translateX(${active.offsetLeft}px)`;
  });

  return (
    <div
      ref={trackRef}
      className={"seg" + (className ? " " + className : "")}
      role="radiogroup"
      aria-label={ariaLabel}
      data-testid={testId}
    >
      <span ref={thumbRef} className="seg-thumb" aria-hidden="true" />
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="radio"
            aria-checked={active}
            className={active ? "active" : ""}
            data-testid={opt.testId}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
