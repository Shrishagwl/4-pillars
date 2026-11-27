import { percent } from '../utils/format.ts';

interface Props {
  value: number; // 0 to 1
  color: string;
  size?: number;
}

/**
 * A ring that fills up to the confidence. It is two circles: a grey track, and a coloured one
 * whose dash length is the share of the circumference we want to show.
 */
export function ConfidenceDonut({ value, color, size = 72 }: Props) {
  const stroke = 8;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="donut" style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--grey-20)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${value * circumference} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="donut__value">{percent(value)}</span>
    </div>
  );
}
