"use client"

import { useEffect, useRef, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"

import TriangleBackground from "./components/TriangleBackground.jsx"
import InputBar from "./components/InputBar.jsx"
import WelcomeMessage from "./components/WelcomeMessage.jsx"
import LLMMarkdownViewer from "./components/MarkdownViewer.jsx"
import UserMessageBubble from "./components/UserMessageBubble.jsx"
import CornerText from "./components/CornerText.jsx"
import LanguageSelector from "./components/LanguageSelector.jsx"
import LoadingAnimation from "./components/LoadingAnimation.jsx"
import ChatContainer from "./components/ChatContainer.jsx"

import circleCuoco from "./assets/circle_cuoco.png"

export default function Page() {

  const [query, setQuery] = useState("")
  const [chatHistory, setChatHistory] = useState([])
  const [uiState, setUiState] = useState("initial")
  const [promptQueue, setPromptQueue] = useState([])
  const [retryDelayMs, setRetryDelayMs] = useState(1000)
  const [retryTimerId, setRetryTimerId] = useState(null)
  // refs to avoid stale closures in timers
  const promptQueueRef = useRef([])
  const retryDelayRef = useRef(1000)
  const retryTimerRef = useRef(null)
  const processQueueRef = useRef(null)
  const isProcessingRef = useRef(false)
  const initializedRef = useRef(false)
  const [lang, setLang] = useState(() => {
    try {
      const stored = typeof window !== "undefined" ? window.localStorage.getItem('cuoco_lang') : null
      if (stored === 'en' || stored === 'pt') return stored
    } catch {}
    return 'en'
  })
  const [showSharedInput, setShowSharedInput] = useState(false)

  const chatContainerRef = useRef(null)
  const bottomRef = useRef(null)     // ← sentinel ref for auto-scroll



  /* -----------------------------------------------------
     LANGUAGE STORAGE
  ----------------------------------------------------- */
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'cuoco_lang') {
        const v = e.newValue
        if (v === 'en' || v === 'pt') setLang(v)
      }
    }
    window.addEventListener('storage', handler)
    return () => window.removeEventListener('storage', handler)
  }, [])

  useEffect(() => {
    try {
      window.localStorage.setItem('cuoco_lang', lang)
    } catch {}
  }, [lang])

  // sync refs with state
  useEffect(() => { promptQueueRef.current = promptQueue }, [promptQueue])
  useEffect(() => { retryDelayRef.current = retryDelayMs }, [retryDelayMs])
  useEffect(() => { retryTimerRef.current = retryTimerId }, [retryTimerId])



  /* -----------------------------------------------------
     SEND QUERY
  ----------------------------------------------------- */
  const handleKeyDown = async (e) => {
    if (e.key === "Enter") {
      await sendQuery()
    }
  }

  const sendQuery = async () => {
    if (!query.trim()) return
    setUiState("loading")
    const q = query
    setQuery("")
    // always enqueue, then process — covers both ready and not-ready backends
    setPromptQueue((prev) => {
      const next = [...prev, q]
      console.log(`[frontend] enqueue prompt:`, q, `| queue size ->`, next.length)
      return next
    })
    // kick processor immediately if not already scheduled or running
    if (!isProcessingRef.current && !retryTimerRef.current) {
      isProcessingRef.current = true
      const tid = setTimeout(() => processQueueRef.current && processQueueRef.current(), 0)
      retryTimerRef.current = tid
    }
  }

  // queue processor kept fresh via ref to avoid stale state
  useEffect(() => {
    if (initializedRef.current) return
    initializedRef.current = true
    processQueueRef.current = async () => {
      const q = promptQueueRef.current[0]
      if (!q) return

      try {
        const res = await fetch("http://localhost:8000/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: q }),
        })

        const data = await res.json().catch(() => ({}))
        const notReady = (!res.ok && (res.status === 503 || (data?.error || "").toLowerCase().includes("initializ")))

        if (notReady) {
          if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
          const nextDelay = Math.min(retryDelayRef.current * 2, 10000)
          const tid = setTimeout(() => processQueueRef.current && processQueueRef.current(), retryDelayRef.current)
          retryTimerRef.current = tid
          setRetryDelayMs(nextDelay)
          return
        }

        const backendResponse = data.response || "No response"
        setChatHistory((prev) => [...prev, { role: "user", text: q }, { role: "bot", text: backendResponse }])
        setUiState("chat")
        // remove processed item
        setPromptQueue((prev) => {
          const removed = prev[0]
          const next = prev.slice(1)
          console.log(`[frontend] dequeue prompt:`, removed, `| queue size ->`, next.length)
          return next
        })
        setRetryDelayMs(1000)
        if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
        retryTimerRef.current = null
        setQuery("")
        // process next if any, otherwise clear processing flag
        if (promptQueueRef.current.length > 0) {
          const tid = setTimeout(() => processQueueRef.current && processQueueRef.current(), 0)
          retryTimerRef.current = tid
        } else {
          isProcessingRef.current = false
        }

      } catch (err) {
        if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
        const nextDelay = Math.min(retryDelayRef.current * 2, 10000)
        const tid = setTimeout(() => processQueueRef.current && processQueueRef.current(), retryDelayRef.current)
        retryTimerRef.current = tid
        setRetryDelayMs(nextDelay)
      }
    }
  }, [])

  /* -----------------------------------------------------
     NEW CHAT (RESET)
  ----------------------------------------------------- */
  const handleNewChat = async () => {
    try {
      // clear backend conversation context
      await fetch("http://localhost:8000/clear", { method: "POST" })
        .catch(() => {})
    } catch {}

    // cancel any retry timer
    if (retryTimerId) clearTimeout(retryTimerId)
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
    setRetryTimerId(null)
    retryTimerRef.current = null
    isProcessingRef.current = false

    // reset client state to initial
    setPromptQueue([])
    promptQueueRef.current = []
    setRetryDelayMs(1000)
    retryDelayRef.current = 1000
    setChatHistory([])
    setQuery("")
    setUiState("initial")
    setShowSharedInput(false)
  }


  /* -----------------------------------------------------
     ⭐ RELIABLE AUTO-SCROLL (NO CRASHES)
  ----------------------------------------------------- */
  useEffect(() => {
    if (!bottomRef.current) return

    // first attempt after paint
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior: "auto" })
    })

    // fallback for images / markdown expansion / animations
    const id = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "auto" })
    }, 80)

    return () => clearTimeout(id)

  }, [chatHistory])



  /* -----------------------------------------------------
     RENDER
  ----------------------------------------------------- */
  return (
    <div className="min-h-screen flex items-center justify-center relative">

      {/* background floating image */}
      <motion.img
        src={circleCuoco}
        alt="Cuoco circle"
        style={{ position: "fixed", top: -200, left: -256, width: 900, height: 900, zIndex: 10, rotate: "-20deg" }}
        initial={{ opacity: 0, y: -24 }}
        animate={{ opacity: 1, y: [ -24, 6, 0 ] }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      />

      <TriangleBackground />

      <motion.div
        style={{ position: 'fixed', top: 16, right: 16, zIndex: 12 }}
        initial={{ opacity: 0, y: -24 }}
        animate={{ opacity: 1, y: [ -24, 6, 0 ] }}
        transition={{ delay: 0.15, duration: 0.7, ease: "easeOut" }}
      >
        <LanguageSelector lang={lang} onChange={setLang} />
      </motion.div>

      <div style={{ position: "fixed", left: 120, bottom: 100, zIndex: 11, pointerEvents: "none" }}>
        <CornerText lang={lang} align="left" gapPx={4} />
      </div>

      {/* MAIN CONTAINER */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
          width: "100%",
          position: "relative",
        }}
      >

        <AnimatePresence mode="wait" onExitComplete={() => {
          if (uiState !== 'initial') setShowSharedInput(true)
        }}>

          {/* INITIAL VIEW */}
          {uiState === "initial" && (
            <motion.div
              key="initial"
              initial={{ opacity: 0, y: -24 }}
              animate={{ opacity: 1, y: [ -24, 6, 0 ] }}
              exit={{ opacity: 0, y: 20 }}
              transition={{ duration: 0.7, ease: "easeOut" }}
              style={{ display: "flex", flexDirection: "column", alignItems: "center", top:"20%" , left: "47%", position: "absolute" }}
            >
              <WelcomeMessage className="mt-6 mb-4" lang={lang} />
              <div style={{ width: "850px", maxWidth: "90vw" }}>
                <InputBar
                  placeholder={lang === 'pt' ? 'Pergunta ao Cuoco!' : 'Ask Cuoco!'}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onNewChat={handleNewChat}
                />
              </div>
            </motion.div>
          )}

          {/* LOADING VIEW */}
          {uiState === "loading" && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              style={{ textAlign: "center", fontSize: "24px", color: "#555" }}
            >
              <div style={{ width: "850px", maxWidth: "90vw", margin: "0 auto", left:"47%", position: "absolute", top: "45%" }}>
                <LoadingAnimation lang={lang} />
              </div>
            </motion.div>
          )}

          {/* CHAT VIEW */}
          {uiState === "chat" && (
            <motion.div
              key="chat"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5 }}
              style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center" }}
            >
              <div
                ref={chatContainerRef}
                style={{
                  marginBottom: "20px",
                  width: "850px",
                  maxWidth: "90vw",
                  overflowY: "auto",
                  position: "absolute",
                  left: "47%",
                  top: "20%",
                  bottom: "12%"
                }}
              >
                {chatHistory.map((msg, i) =>
                  msg.role === "bot" ? (
                    <LLMMarkdownViewer key={i} text={msg.text} widthPx={850} />
                  ) : (
                    <div key={i} style={{ margin: "10px 0" }}>
                      <UserMessageBubble text={msg.text} maxWidthPx={Math.floor(850 * 2 / 3)} />
                    </div>
                  )
                )}

                {/* sentinel for auto-scroll */}
                <div ref={bottomRef} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* SHARED INPUT BAR */}
        <AnimatePresence>
          {showSharedInput && uiState !== "initial" && (
            <motion.div
              key="shared-input"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              style={{ position: "absolute", left: "47%", top: "90%" }}
            >
              <div style={{ width: "850px", maxWidth: "90vw" }}>
                <InputBar
                  placeholder={lang === 'pt' ? 'Pergunta ao Cuoco!' : 'Ask Cuoco!'}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onNewChat={handleNewChat}
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
