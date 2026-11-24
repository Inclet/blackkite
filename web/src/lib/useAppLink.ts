import type { MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router';

export interface AppLink {
  href: string;
  onClick: (event: MouseEvent<HTMLAnchorElement>) => void;
}

/** True when the click should be left to the browser (new tab, download, etc.). */
export function isModifiedClick(event: MouseEvent): boolean {
  return event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
}

/** In-app links keep the query string (?fixture=…) and navigate without a reload. */
export function useAppLink(): (to: string, options?: { replace?: boolean; onNavigate?: () => void }) => AppLink {
  const navigate = useNavigate();
  const { search } = useLocation();
  return (to, options) => {
    const href = `${to}${search}`;
    return {
      href,
      onClick: (event) => {
        if (event.defaultPrevented || isModifiedClick(event)) return;
        event.preventDefault();
        options?.onNavigate?.();
        navigate(href, { replace: options?.replace });
      },
    };
  };
}
