import React, { useEffect, useMemo, useState } from "react";

export default function CornerText({ lang = 'en', align = 'center', gapPx = 6, charDelayMs = 30, lineDelayMs = 0, startDelayMs = 500 }) {
  const lines = useMemo(() => {
    const firstLine = lang === 'pt' ? 'TRAZIDO POR' : 'POWERED BY'
    const secondLine = 'OS TRAQUINAS'
    const thirdLine = 'DEI FCTUC'
    return [firstLine, secondLine, thirdLine]
  }, [lang])

  const [displayed, setDisplayed] = useState(['', '', ''])
  const [hasAnimated, setHasAnimated] = useState(false)

  useEffect(() => {
    let active = true
    const typeLine = async (lineIdx) => {
      const text = lines[lineIdx]
      for (let i = 0; i <= text.length && active; i++) {
        setDisplayed((prev) => {
          const next = [...prev]
          next[lineIdx] = text.slice(0, i)
          return next
        })
        await new Promise((r) => setTimeout(r, charDelayMs))
      }
      if (active) await new Promise((r) => setTimeout(r, lineDelayMs))
      if (active && lineIdx < lines.length - 1) {
        await typeLine(lineIdx + 1)
      } else if (active) {
        setHasAnimated(true)
      }
    }
    const start = async () => {
      if (startDelayMs > 0) {
        await new Promise((r) => setTimeout(r, startDelayMs))
      }
      if (active) await typeLine(0)
    }
    start()
    return () => { active = false }
    // Run only on initial mount to avoid retriggering on language change
  }, [])

  // On language change after initial animation, update text instantly without retyping
  useEffect(() => {
    if (hasAnimated) {
      setDisplayed([lines[0], lines[1], lines[2]])
    }
  }, [lang, hasAnimated, lines])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: align === 'center' ? 'center' : (align === 'right' ? 'flex-end' : 'flex-start'), gap: gapPx }}>
      {/* Reserve fixed height per line to avoid layout shift */}
      {/* Line 1: Panton Thin */}
      <div style={{ height: '38px', display: 'flex', alignItems: 'baseline' }}>
        <div style={{ fontFamily: 'Panton, sans-serif', fontWeight: 100, fontStyle: 'normal', fontSize: '32px', lineHeight: 1.2, color: '#000', whiteSpace: 'pre' }}>
          {displayed[0]}
        </div>
      </div>

      {/* Line 2: Panton Bold (grey) */}
      <div style={{ height: '48px', display: 'flex', alignItems: 'baseline' }}>
        <div style={{ fontFamily: 'Panton, sans-serif', fontWeight: 800, fontStyle: 'normal', fontSize: '40px', lineHeight: 1.2, color: '#6b7280', whiteSpace: 'pre' }}>
          {displayed[1]}
        </div>
      </div>

      {/* Line 3: DEI (Bold while typing) + FCTUC (Regular) */}
      <div style={{ height: '44px', display: 'flex', alignItems: 'baseline' }}>
        <div style={{ fontSize: '36px', lineHeight: 1.2, color: '#000', whiteSpace: 'pre' }}>
          {/* While typing, render bold for "DEI" portion and regular for the rest */}
          {displayed[2].length < lines[2].length ? (
            (() => {
              const full = lines[2];
              const typed = displayed[2];
              const deiLen = 3; // "DEI" length
              const deiTyped = typed.slice(0, Math.min(deiLen, typed.length));
              const restTyped = typed.slice(Math.min(deiLen, typed.length));
              return (
                <>
                  <span style={{ fontFamily: 'Panton, sans-serif', fontWeight: 700, fontStyle: 'normal', color: '#000' }}>{deiTyped}</span>
                  <span style={{ fontFamily: 'Panton, sans-serif', fontWeight: 400, fontStyle: 'normal', color: '#000' }}>{restTyped}</span>
                </>
              );
            })()
          ) : (
            <>
              <span style={{ fontFamily: 'Panton, sans-serif', fontWeight: 700, fontStyle: 'normal', color: '#000' }}>DEI</span>
              <span style={{ fontFamily: 'Panton, sans-serif', fontWeight: 400, fontStyle: 'normal', color: '#000' }}> FCTUC</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
