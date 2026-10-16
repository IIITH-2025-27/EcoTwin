import { useEffect, useRef, useState, type RefObject } from 'react';
import type React from 'react';
import { useMapStore } from '@/store/mapStore';

// Movement (px) before a press counts as a drag rather than a tap
const DRAG_THRESHOLD_PX = 6;
// Released below this fraction → minimize; above SNAP_FULL_ABOVE → fill the map area
const MINIMIZE_BELOW = 0.2;
const SNAP_FULL_ABOVE = 0.92;

/**
 * Drag-to-resize for the mobile bottom sheet. `containerRef` is the area the
 * sheet is anchored to; heights are fractions of it. Returns pointer handlers to
 * spread onto any drag surface (sheet handle, bottom tab bar) and the live
 * height while a drag is in progress (null otherwise).
 */
export function useSheetDrag(containerRef: RefObject<HTMLElement>) {
  const [liveHeight, setLiveHeight] = useState<number | null>(null);
  const cleanup = useRef<(() => void) | null>(null);

  useEffect(() => () => cleanup.current?.(), []);

  const onPointerDown = (e: React.PointerEvent<HTMLElement>) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    cleanup.current?.();

    const { isSidebarCollapsed, sheetHeight } = useMapStore.getState();
    const startY = e.clientY;
    const startHeight = isSidebarCollapsed ? 0 : sheetHeight;
    const containerHeight = containerRef.current?.clientHeight || window.innerHeight;
    const heightAt = (clientY: number) =>
      Math.min(1, Math.max(0, startHeight + (startY - clientY) / containerHeight));
    let active = false;

    // Listen on window so the drag keeps tracking wherever the finger goes
    const onMove = (ev: PointerEvent) => {
      if (!active) {
        if (Math.abs(ev.clientY - startY) < DRAG_THRESHOLD_PX) return;
        active = true;
      }
      setLiveHeight(heightAt(ev.clientY));
    };

    const onEnd = (ev: PointerEvent) => {
      cleanup.current?.();
      if (!active) return;
      const final = heightAt(ev.clientY);
      setLiveHeight(null);
      const { setSidebarCollapsed, setSheetHeight } = useMapStore.getState();
      if (final < MINIMIZE_BELOW) {
        // Keep the last height so Expand / a tab tap restores it
        setSidebarCollapsed(true);
      } else {
        setSheetHeight(final > SNAP_FULL_ABOVE ? 1 : final);
        setSidebarCollapsed(false);
      }
      // A drag that ends over a button must not also trigger it
      const swallowClick = (ce: MouseEvent) => {
        ce.stopPropagation();
        ce.preventDefault();
      };
      window.addEventListener('click', swallowClick, { capture: true, once: true });
      setTimeout(() => window.removeEventListener('click', swallowClick, true), 0);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onEnd);
    window.addEventListener('pointercancel', onEnd);
    cleanup.current = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      window.removeEventListener('pointercancel', onEnd);
      cleanup.current = null;
    };
  };

  return { handlers: { onPointerDown }, liveHeight };
}
