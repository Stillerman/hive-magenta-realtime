// Copyright 2026 Google LLC. Apache-2.0.
import { useEffect, useRef } from "react";

/** Quiet audio-reactive backdrop: staff lines and a breathing signal trace. */
export function Visualizer({ levelRef, count }: { levelRef: { current: number }; count: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const countRef = useRef(count);
  countRef.current = count;

  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let t = 0;
    let smooth = 0;

    const resize = () => {
      canvas.width = window.innerWidth * devicePixelRatio;
      canvas.height = window.innerHeight * devicePixelRatio;
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = () => {
      t += 0.012;
      smooth += (levelRef.current - smooth) * 0.15;
      const W = canvas.width, H = canvas.height;
      const dpr = devicePixelRatio;
      ctx.fillStyle = "#0b0b09";
      ctx.fillRect(0, 0, W, H);

      const top = H * 0.22;
      const bottom = H * 0.82;
      const rows = 8;
      ctx.lineWidth = 1 * dpr;
      for (let i = 0; i <= rows; i++) {
        const y = top + ((bottom - top) / rows) * i;
        ctx.beginPath();
        ctx.moveTo(W * 0.05, y);
        ctx.lineTo(W * 0.95, y);
        ctx.strokeStyle = i === Math.floor(rows / 2)
          ? "rgba(238, 232, 219, 0.11)"
          : "rgba(238, 232, 219, 0.055)";
        ctx.stroke();
      }

      const cx = W * 0.5;
      const cy = H * 0.53;
      const active = Math.max(1, countRef.current);
      const amp = (14 + Math.min(90, active * 5) + smooth * 420) * dpr;
      const width = W * 0.78;
      const points = 96;

      ctx.beginPath();
      for (let i = 0; i <= points; i++) {
        const pct = i / points;
        const x = cx - width / 2 + pct * width;
        const falloff = Math.sin(Math.PI * pct);
        const y = cy +
          Math.sin(pct * Math.PI * (2.5 + active * 0.18) + t * 3.2) * amp * falloff * 0.42 +
          Math.sin(pct * Math.PI * (7 + active * 0.1) - t * 2.1) * amp * falloff * 0.12;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = `rgba(230, 222, 204, ${0.16 + Math.min(0.28, smooth * 1.9)})`;
      ctx.lineWidth = (1.2 + smooth * 7) * dpr;
      ctx.lineCap = "round";
      ctx.stroke();

      const bars = Math.min(28, countRef.current);
      for (let i = 0; i < bars; i++) {
        const x = W * 0.12 + (i / Math.max(1, bars - 1)) * W * 0.76;
        const h = (18 + Math.sin(t * 2 + i) * 8 + smooth * 170) * dpr;
        ctx.beginPath();
        ctx.moveTo(x, H * 0.89);
        ctx.lineTo(x, H * 0.89 - h);
        ctx.strokeStyle = "rgba(177, 163, 133, 0.18)";
        ctx.lineWidth = 1 * dpr;
        ctx.stroke();
      }

      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, [levelRef]);

  return <canvas ref={ref} className="viz" />;
}
