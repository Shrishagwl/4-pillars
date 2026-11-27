import type { View } from '../types.ts';
import { Icon } from './Icon.tsx';

interface Props {
  view: View;
  onViewChange: (view: View) => void;
  search: string;
  onSearchChange: (text: string) => void;
}

const TABS: { id: View | 'scenarios' | 'evaluation'; label: string; ready: boolean }[] = [
  { id: 'overview', label: 'Overview', ready: true },
  { id: 'incidents', label: 'Incidents', ready: true },
  { id: 'scenarios', label: 'Scenarios', ready: false }, // task 7
  { id: 'evaluation', label: 'Evaluation', ready: false }, // task 10
];

export function TopNav({ view, onViewChange, search, onSearchChange }: Props) {
  return (
    <header className="top-nav">
      <div className="brand">
        <span className="brand__mark">4P</span>
        <span className="brand__name">4 Pillars</span>
        <span className="brand__divider" />
        <img className="brand__telstra" src="/brand/telstra-logo.png" alt="Telstra" />
        <span className="brand__event">IoT Fest 2026</span>
      </div>

      <nav className="tabs" aria-label="Main">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`tab${tab.id === view ? ' tab--active' : ''}`}
            disabled={!tab.ready}
            title={tab.ready ? undefined : 'Coming soon'}
            onClick={() => tab.ready && onViewChange(tab.id as View)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <label className="search">
        <Icon name="search" />
        <input
          type="search"
          placeholder="Search suburb, incident or meter"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </label>

      <button type="button" className="icon-button" aria-label="Notifications">
        <Icon name="bell" size={20} />
      </button>
      <span className="avatar" title="SR">
        SR
      </span>
    </header>
  );
}
