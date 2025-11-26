import TriangleBackground from "./components/TriangleBackground.jsx"

export default function Page() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <TriangleBackground />
      <div className="relative z-10 text-center p-8">
        <h1 className="text-4xl font-bold mb-4">Triangle Background</h1>
        <p className="text-lg opacity-80">Watch the triangles gradually change colors</p>
      </div>
    </div>
  )
}
