"use client"

import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"

import TriangleBackground from "./components/TriangleBackground.jsx"
import RoundedInput from "./components/InputBar.jsx"
import WelcomeMessage from "./components/WelcomeMessage.jsx"
import LLMMarkdownViewer from "./components/ChatViewer.jsx"
import circleCuoco from "./assets/circle_cuoco.png"

export default function Page() {
  const [query, setQuery] = useState("")
  const [chatHistory, setChatHistory] = useState([]) // stores conversation
  const [uiState, setUiState] = useState("initial") // "initial" | "loading" | "chat"

  const handleKeyDown = async (e) => {
    if (e.key === "Enter") {
      await sendQuery()
    }
  }

  const sendQuery = async () => {
    if (!query.trim()) return

    // switch to loading state
    setUiState("loading")

    try {
      const res = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query }),
      })

      const data = await res.json()
      const backendResponse = data.response || "No response from backend"

      // update chat history
      setChatHistory((prev) => [...prev, { role: "user", text: query }, { role: "bot", text: backendResponse }])

      // switch to chat state
      setUiState("chat")
    } catch (err) {
      console.error("Error:", err)
      setChatHistory((prev) => [...prev, { role: "user", text: query }, { role: "bot", text: "An error occurred." }])
      setUiState("chat")
    }

    setQuery("") // clear input
  }

  /*          
  style={{ position: "fixed", top: -200, left: -256, width: 900, height: 900, zIndex: 10, rotate: "-20deg" }}
  */

  return (
    <div className="min-h-screen flex items-center justify-center relative">
    <motion.img
      src={circleCuoco}
      alt="Cuoco circle"
      style={{ position: "fixed", top: -200, left: -256, width: 900, height: 900, zIndex: 10, rotate: "-20deg" }}
      initial={{ opacity: 0, y: -24 }}
      animate={{ opacity: 1, y: [ -24, 6, 0 ] }}
      transition={{ duration: 0.7, ease: "easeOut" }}
/>
      <TriangleBackground />

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
        <AnimatePresence exitBeforeEnter>
          {uiState === "initial" && (
            <motion.div
              key="initial"
              initial={{ opacity: 0, y: -24 }}
              animate={{ opacity: 1, y: [ -24, 6, 0 ] }}
              transition={{ delay: 0.1, duration: 0.7, ease: "easeOut" }}
              exit={{ opacity: 0, y: 20 }}
              style={{ display: "flex", flexDirection: "column", alignItems: "center", top:"20%" , left: "47%", position: "absolute" }}
            >
              <div style={{ width: "auto" }}>
                <WelcomeMessage className="mt-6 mb-4" />
              </div>
              <div style={{ width: "850px", maxWidth: "90vw" }}>
                <RoundedInput
                  placeholder="Ask Cuoco!"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                />
              </div>
            </motion.div>
          )}

          {uiState === "loading" && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              style={{ textAlign: "center", fontSize: "24px", color: "#555" }}
            >
              Processing your query...
            </motion.div>
          )}

          {uiState === "chat" && (
            <motion.div
              key="chat"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.5 }}
              style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center" }}
            >
              <div style={{ marginBottom: "20px", width: "60%", maxHeight: "50vh", overflowY: "auto" }}>
                {chatHistory.map((msg, i) => (
                  msg.role === "bot" ? (
                    <LLMMarkdownViewer key={i} text={msg.text} widthPx={1000} />
                  ) : (
                    <div
                      key={i}
                      style={{
                        margin: "10px 0",
                        alignSelf: "flex-end",
                        background: "#ffe0dc",
                        padding: "12px 20px",
                        borderRadius: "20px",
                        boxShadow: "0 2px 6px rgba(0,0,0,0.1)",
                        fontSize: "18px",
                        lineHeight: "1.4",
                      }}
                    >
                      {msg.text}
                    </div>
                  )
                ))}
              </div>

              {/* Bottom input bar for initial state */}
              <div style={{ position: "fixed", left: 0, right: 0, bottom: 20, display: "flex", justifyContent: "center" }}>
                <div style={{ width: "1000px", maxWidth: "90vw" }}>
                  <RoundedInput
                    placeholder="Ask Cuoco!"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                  />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
