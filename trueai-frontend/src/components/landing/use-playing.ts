'use client'

import { useEffect, useState, type RefObject } from 'react'

/**
 * Playback state for the landing page's looping illustrations.
 *
 *   playing        true while the element is on screen and motion is allowed;
 *                  the illustration only advances while this is true
 *   reducedMotion  the visitor asked for reduced motion: show the finished
 *                  picture instead of playing it
 */
export function usePlaying(ref: RefObject<HTMLElement | null>): { playing: boolean; reducedMotion: boolean } {
  const [playing, setPlaying] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const observer = new IntersectionObserver(([entry]) => {
      setReducedMotion(query.matches)
      setPlaying(entry.isIntersecting && !query.matches)
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [ref])

  return { playing, reducedMotion }
}
