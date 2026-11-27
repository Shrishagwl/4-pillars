/**
 * The line icons from the Figma design, drawn as inline SVG so we need no icon library.
 * Use it like: <Icon name="map" size={16} />
 */

const PATHS = {
  map: ['M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z', 'M9 4v14M15 6v14'],
  search: ['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z', 'm21 21-4.3-4.3'],
  bell: ['M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9', 'M10.3 21a1.9 1.9 0 0 0 3.4 0'],
  play: ['m6 4 14 8-14 8z'],
  zap: ['M13 2 3 14h9l-1 8 10-12h-9l1-8z'],
  check: ['M20 6 9 17l-5-5'],
  arrowLeft: ['M19 12H5', 'm12 19-7-7 7-7'],
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps {
  name: IconName;
  size?: number;
}

export function Icon({ name, size = 16 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
