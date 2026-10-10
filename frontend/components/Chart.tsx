"use client";

import { useEffect, useRef, useState } from "react";
import { shortDate } from "@/lib/format";

type Point = { date: string; value: number | null };

type Props = {
  data: Point[];
  kind?: "line" | "bar";
  label: string; // for screen readers and hover readouts, e.g. "Sleep"
  unit: string;
  format: (value: number) => string;
  normal?: number | null; // the user's baseline: dashed line labelled at its end
  guide?: { value: number; label: string }; // a fixed threshold, drawn the same way
  flag?: (value: number) => boolean; // marks a point as below normal (amber)
  flagLabel?: string; // what an amber point means, shown under the chart when there is one
};

const HEIGHT = 164;
const M = { top: 26, right: 78, bottom: 24, left: 30 }; // the top margin leaves room for the day readout
const TIP_HALF_WIDTH = 56;
const LABEL_GAP = 12;

function niceStep(range: number, count: number) {
  const raw = range / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  return (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    setWidth(Math.floor(ref.current.getBoundingClientRect().width));
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export default function Chart({ data, kind = "line", label, unit, format, normal, guide, flag, flagLabel }: Props) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState<number | null>(null); // the day under the pointer or finger
  const values = data.flatMap((d) => (d.value == null ? [] : [d.value]));

  let body = null;
  let tip = null;
  if (width > 0 && values.length > 0) {
    const refs = [normal, guide?.value].filter((v): v is number => v != null);
    const all = [...values, ...refs];
    let lo = kind === "bar" ? 0 : Math.min(...all);
    let hi = Math.max(...all);
    const pad = Math.max(hi - lo, 1) * 0.14;
    if (kind === "line") lo -= pad;
    hi += pad;

    const plotW = width - M.left - M.right;
    const plotH = HEIGHT - M.top - M.bottom;
    const band = plotW / data.length;
    const x = (i: number) => M.left + (i + 0.5) * band;
    const y = (v: number) => M.top + (1 - (v - lo) / (hi - lo)) * plotH;

    const step = niceStep(hi - lo, 3);
    const ticks: number[] = [];
    for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(Number(t.toPrecision(10)));

    // Line path, broken where a day has no reading
    let path = "";
    let pen = false;
    data.forEach((d, i) => {
      if (d.value == null) return void (pen = false);
      path += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`;
      pen = true;
    });

    let lastIndex = -1;
    data.forEach((d, i) => { if (d.value != null) lastIndex = i; });
    const last = data[lastIndex];
    const every = Math.ceil(data.length / Math.max(2, Math.min(7, Math.floor(plotW / 52))));

    // Labels sit at the right end of what they describe; nudge them apart if they collide
    const labels: { y: number; text: string; className: string }[] = [];
    if (normal != null) labels.push({ y: y(normal), text: `Normal ${format(normal)}`, className: "chart-ref" });
    if (guide) labels.push({ y: y(guide.value), text: guide.label, className: "chart-ref" });
    labels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++)
      if (labels[i].y - labels[i - 1].y < LABEL_GAP) labels[i].y = labels[i - 1].y + LABEL_GAP;

    const right = M.left + plotW;
    const point = active != null ? data[active] : null;
    if (point && active != null) {
      tip = (
        <div className="chart-tip" style={{ left: Math.max(TIP_HALF_WIDTH, Math.min(width - TIP_HALF_WIDTH, x(active))) }}>
          {shortDate(point.date)} · {point.value == null ? "no reading" : <b>{format(point.value)} {unit}</b>}
        </div>
      );
    }

    const pointAt = (clientX: number, svg: SVGSVGElement) => {
      const i = Math.floor((clientX - svg.getBoundingClientRect().left - M.left) / band);
      setActive(i >= 0 && i < data.length ? i : null);
    };

    body = (
      <svg
        width={width} height={HEIGHT} role="img"
        aria-label={`${label}, last ${data.length} days${last?.value != null ? `, latest ${format(last.value)} ${unit}` : ""}`}
        onPointerMove={(e) => pointAt(e.clientX, e.currentTarget)}
        onPointerDown={(e) => pointAt(e.clientX, e.currentTarget)}
        // A finger lifting also "leaves": keep the readout on touch screens until the next tap
        onPointerLeave={(e) => { if (e.pointerType === "mouse") setActive(null); }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="chart-grid" x1={M.left} x2={right} y1={y(t)} y2={y(t)} />
            <text className="chart-tick" x={M.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle">
              {t >= 1000 ? `${t / 1000}k` : t}
            </text>
          </g>
        ))}

        {data.map((d, i) =>
          (data.length - 1 - i) % every === 0 ? (
            <text key={d.date} className="chart-tick" x={x(i)} y={HEIGHT - 6} textAnchor="middle">
              {shortDate(d.date)}
            </text>
          ) : null,
        )}

        {refs.map((v, i) => (
          <line key={i} className="chart-dash" x1={M.left} x2={right} y1={y(v)} y2={y(v)} />
        ))}

        {kind === "bar"
          ? data.map((d, i) =>
              d.value == null ? null : (
                <line
                  key={d.date}
                  className={flag?.(d.value) ? "chart-bar is-amber" : "chart-bar"}
                  x1={x(i)} x2={x(i)} y1={y(0)} y2={y(d.value)}
                />
              ),
            )
          : <path className="chart-line" d={path} />}

        {kind === "line" &&
          data.map((d, i) =>
            d.value != null && (flag?.(d.value) || i === lastIndex) ? (
              <circle
                key={d.date}
                className={flag?.(d.value) ? "chart-dot is-amber" : "chart-dot"}
                cx={x(i)} cy={y(d.value)} r={2.5}
              />
            ) : null,
          )}

        {labels.map((l) => (
          <text key={l.text} className={l.className} x={right + 8} y={l.y} dominantBaseline="middle">
            {l.text}
          </text>
        ))}

        {/* The day being pointed at */}
        {active != null && (
          <g className="chart-cursor">
            <line x1={x(active)} x2={x(active)} y1={M.top} y2={M.top + plotH} />
            {kind === "line" && point?.value != null && <circle cx={x(active)} cy={y(point.value)} r={4} />}
          </g>
        )}
      </svg>
    );
  }

  return (
    <>
      <div ref={ref} className="chart" style={{ height: HEIGHT }}>
        {tip}
        {body ?? (values.length === 0 ? <p className="empty">No readings in this period</p> : null)}
      </div>
      {flagLabel && flag && values.some(flag) && <p className="chart-key"><i />{flagLabel}</p>}
    </>
  );
}
