import type { Route } from '../api/types';

export function routeStyle(route: string): string {
  if (route === 'AUTO_APPROVE') return 'bg-green-100 text-green-800 border-green-300';
  if (route === 'HUMAN_REVIEW') return 'bg-orange-100 text-orange-800 border-orange-300';
  if (route === 'REJECT') return 'bg-red-100 text-red-800 border-red-300';
  return 'bg-gray-100 text-gray-800 border-gray-300';
}

const LABELS: Record<Route, string> = {
  AUTO_APPROVE: 'APPROVED',
  HUMAN_REVIEW: 'NEEDS REVIEW',
  REJECT: 'REJECTED',
};

export default function RouteChip({ route }: { route: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border whitespace-nowrap ${routeStyle(route)}`}>
      {LABELS[route as Route] ?? route}
    </span>
  );
}
