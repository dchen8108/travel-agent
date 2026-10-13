import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface ScrollState {
  canScrollDown: boolean;
  canScrollUp: boolean;
}

const INITIAL_SCROLL_STATE: ScrollState = {
  canScrollDown: false,
  canScrollUp: false,
};

export function ScrollableDetailList({ children }: Props) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const [scrollState, setScrollState] = useState<ScrollState>(INITIAL_SCROLL_STATE);

  useEffect(() => {
    const node = listRef.current;
    if (!node) {
      return;
    }
    const scrollNode = node;

    let animationFrame = 0;

    function updateScrollState() {
      cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(() => {
        const threshold = 2;
        const canScrollUp = scrollNode.scrollTop > threshold;
        const canScrollDown = scrollNode.scrollTop + scrollNode.clientHeight < scrollNode.scrollHeight - threshold;
        setScrollState((current) => (
          current.canScrollUp === canScrollUp && current.canScrollDown === canScrollDown
            ? current
            : { canScrollUp, canScrollDown }
        ));
      });
    }

    updateScrollState();
    scrollNode.addEventListener("scroll", updateScrollState, { passive: true });

    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateScrollState);
    resizeObserver?.observe(scrollNode);
    const mutationObserver = typeof MutationObserver === "undefined" ? null : new MutationObserver(updateScrollState);
    mutationObserver?.observe(scrollNode, { childList: true, subtree: true });
    if (!resizeObserver) {
      window.addEventListener("resize", updateScrollState);
    }

    return () => {
      cancelAnimationFrame(animationFrame);
      scrollNode.removeEventListener("scroll", updateScrollState);
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
      if (!resizeObserver) {
        window.removeEventListener("resize", updateScrollState);
      }
    };
  }, []);

  return (
    <div
      className="scroll-affordance"
      data-can-scroll-down={scrollState.canScrollDown}
      data-can-scroll-up={scrollState.canScrollUp}
    >
      <div ref={listRef} className="detail-list">
        {children}
      </div>
    </div>
  );
}
