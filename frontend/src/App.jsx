import { useState, useRef, useEffect } from 'react'

function Message({ role, text }) {
  return (
    <div className={`msg ${role}`}>
      <div className="bubble">{text}</div>
    </div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([
    { role: 'bot', text: 'Olá! Como posso ajudar? 😊' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const listRef = useRef(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  async function sendMessage(e) {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || loading) return

    const userMsg = { role: 'user', text: trimmed }
    setMessages((m) => [...m, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed })
      })

      if (!res.ok) throw new Error(`Request failed: ${res.status}`)
      const data = await res.json()

      // Expecting shape: { reply: string } or more
      const reply = data.reply || data.text || JSON.stringify(data)
      setMessages((m) => [...m, { role: 'bot', text: reply }])
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: 'bot', text: 'Erro ao contactar o servidor. Verifica o backend.' },
      ])
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Knowledge-and-Language Chatbot</h1>
      </header>
      <main>
        <div className="chat" ref={listRef}>
          {messages.map((m, i) => (
            <Message key={i} role={m.role} text={m.text} />
          ))}
          {loading && <div className="msg bot"><div className="bubble loading">A pensar…</div></div>}
        </div>
        <form className="composer" onSubmit={sendMessage}>
          <input
            type="text"
            placeholder="Escreve a tua pergunta…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" disabled={loading || !input.trim()}>
            Enviar
          </button>
        </form>
      </main>
      <footer>
        <small>Dev server proxies /api → backend. Configure VITE_BACKEND_URL as needed.</small>
      </footer>
    </div>
  )
}
