// Updated App.jsx with LLMMarkdownViewer replacing message container

"use client"

import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"

import TriangleBackground from "./components/TriangleBackground.jsx"
import RoundedInput from "./components/InputBar.jsx"
import WelcomeMessage from "./components/WelcomeMessage.jsx"
import LLMMarkdownViewer from "./components/ChatViewer.jsx"

import cuoco from "./assets/cuoco.svg"

export default function Page() {
  const [query, setQuery] = useState("")
  const [chatHistory, setChatHistory] = useState([])
  const [uiState, setUiState] = useState("initial")

  const handleKeyDown = async (e) => {
    if (e.key === "Enter") {
      await sendQuery()
    }
  }

  const sendQuery = async () => {
    if (!query.trim()) return
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

      setChatHistory((prev) => [
        ...prev,
        { role: "user", text: query },
        { role: "bot", text: backendResponse },
      ])

      setUiState("chat")
    } catch (err) {
      console.error("Error:", err)
      setChatHistory((prev) => [
        ...prev,
        { role: "user", text: query },
        { role: "bot", text: "An error occurred." },
      ])
      setUiState("chat")
    }

    setQuery("")
  }

  return (
    <div className="min-h-screen flex items-center justify-center relative">
      <TriangleBackground />

      <div className="flex flex-col items-center justify-center h-screen w-full relative">
        <AnimatePresence exitBeforeEnter>
          {uiState === "initial" && (
            <motion.div
              key="initial"
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              transition={{ duration: 0.5 }}
              className="flex flex-col items-center"
            >
              <img
                src={cuoco || "/placeholder.svg"}
                alt="Cuoco"
                style={{ marginTop: "-10vh", width: "200px", height: "200px" }}
              />
              <WelcomeMessage className="mt-6 mb-4" />

              <div style={{ width: "1000px", maxWidth: "90vw" }}>
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
              className="text-center text-2xl text-gray-600"
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
              className="w-full flex flex-col items-center"
            >
              <div className="mb-5 w-3/5 max-h-[50vh] overflow-y-auto">
                {chatHistory.map((msg, i) => (
                  <div key={i} className="my-2 w-full flex justify-center">
                    <LLMMarkdownViewer text={msg.text} />
                  </div>
                ))}
              </div>

              <div style={{ width: "900px", maxWidth: "90vw" }}>
                <RoundedInput
                  placeholder="Ask Cuoco!"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}