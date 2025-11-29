import { useEffect, useLayoutEffect, useRef, useState } from "react";

export default function ChatContainer({ chatHistory, renderMessage }) {
  const chatRef = useRef(null);
  const bottomRef = useRef(null);
  const [shouldStick, setShouldStick] = useState(true);

  // Detect if the user is at the bottom
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        setShouldStick(entry.isIntersecting);
      },
      { root: el, threshold: 1.0 }
    );

    if (bottomRef.current) observer.observe(bottomRef.current);

    return () => observer.disconnect();
  }, []);

  // Scroll anytime messages change AND we are stuck at bottom
  useLayoutEffect(() => {
    if (!shouldStick) return;
    if (!bottomRef.current) return;

    requestAnimationFrame(() => {
      bottomRef.current.scrollIntoView({ behavior: "auto" });
      setTimeout(() => {
        bottomRef.current.scrollIntoView({ behavior: "auto" });
      }, 50);
    });
  }, [chatHistory, shouldStick]);

  return (
    <div
      ref={chatRef}
      className="overflow-y-scroll w-full h-full"
      style={{ scrollBehavior: "auto" }}
    >
      {chatHistory.map((msg, index) => renderMessage(msg, index))}

      <div ref={bottomRef} style={{ height: 1 }} />
    </div>
  );
}
