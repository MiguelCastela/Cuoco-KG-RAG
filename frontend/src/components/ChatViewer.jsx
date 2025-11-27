import React from "react";
import ReactMarkdown from "react-markdown";
import { motion } from "framer-motion";

// LLMMarkdownViewer displays markdown text centered inside a transparent container
export default function LLMMarkdownViewer({ text }) {
  return (
    <div className="w-full flex justify-center">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="prose prose-neutral dark:prose-invert max-w-2xl text-center bg-transparent"
      >
        <ReactMarkdown>{text}</ReactMarkdown>
      </motion.div>
    </div>
  );
}
