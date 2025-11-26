import TriangleBackground from "./components/TriangleBackground.jsx"
import RoundedInput from "./components/InputBar.jsx"
import WelcomeMessage from "./components/WelcomeMessage.jsx"

import cuoco from "./assets/cuoco.svg"

export default function Page() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <TriangleBackground />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", height: "100vh" }}>
            <img
              src={cuoco}
              alt="Cuoco"
              style={{ marginTop: "-10vh", width: "200px", height: "200px" }}
            />
          <WelcomeMessage className="mt-6 mb-4" />
          <RoundedInput placeholder="Ask Cuoco" />
        </div>
    </div>
  )
}
