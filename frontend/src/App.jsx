import { useState } from "react";

import TriangleBackground from "./components/TriangleBackground.jsx";
import RoundedInput from "./components/InputBar.jsx";
import WelcomeMessage from "./components/WelcomeMessage.jsx";

import cuoco from "./assets/cuoco.svg";

export default function Page() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState(""); // to display backend result

  const handleKeyDown = async (e) => {
    if (e.key === "Enter") {
      await sendQuery();
    }
  };

  const sendQuery = async () => {
    if (!query.trim()) return;

    try {
      const res = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query }),
      });

      const data = await res.json();
      setResponse(data.response || "No response from backend");

    } catch (err) {
      console.error("Error:", err);
      setResponse("An error occurred.");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <TriangleBackground />
      <div 
        style={{ 
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh"
        }}>
        
        <img
          src={cuoco}
          alt="Cuoco"
          style={{ marginTop: "-10vh", width: "200px", height: "200px" }}
        />

        <WelcomeMessage className="mt-6 mb-4" />

        <RoundedInput
          placeholder="Ask Cuoco!"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        {/* Display backend response */}
        {response && (
          <div style={{
            marginTop: "30px",
            maxWidth: "60%",
            background: "white",
            padding: "20px",
            borderRadius: "20px",
            boxShadow: "0 4px 10px rgba(0,0,0,0.1)",
            fontSize: "20px",
            lineHeight: "1.5",
          }}>
            {response}
          </div>
        )}
      </div>
    </div>
  );
}
