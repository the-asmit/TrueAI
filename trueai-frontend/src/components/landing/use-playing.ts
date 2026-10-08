'use client'

import { useEffect, useState, type RefObject } from 'react'

/**
 * True while the element is on screen and the visitor has not asked for reduced
 * motion. The landing page's looping illustrations only advance while this is true.
 */
export function usePlaying(ref: RefObject<HTMLElement | null>): boolean {
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const observer = new IntersectionObserver(([entry]) => setPlaying(entry.isIntersecting && !reducedMotion.matches))
    observer.observe(node)
    return () => observer.disconnect()
  }, [ref])

  return playing
}
