import React, { useMemo } from "react";
import cuoco from "../assets/cuoco.svg";

const defaultPhrases = [
  "What are we cooking today?",
  "Ready to make something delicious?",
  "What’s in your kitchen right now?",
  "Need a recipe or cooking advice?",
  "What are you craving today?",
  "Let’s turn ingredients into something amazing. What do you have?",
  "Breakfast, lunch, or dinner — what’s the plan?",
  "Do you want a quick meal or something fancy?",
  "Tell me what ingredients you’ve got!",
  "Looking for a recipe or a cooking tip?",
  "What dish are you in the mood for?",
  "Cooking time! What can I help you make?",
  "Are you cooking for one or for a crowd?",
  "Any dietary preferences I should know about?",
  "Sweet or savory — what are you thinking?",
  "O que vamos cozinhar hoje?",
  "Pronto para fazer algo delicioso?",
  "O que você tem na sua cozinha agora?",
  "Quer uma receita ou uma dica de cozinha?",
  "Do que você está com vontade hoje?",
  "Vamos transformar ingredientes em algo incrível. O que você tem aí?",
  "Café da manhã, almoço ou jantar — qual é o plano?",
  "Quer algo rápido ou algo mais elaborado?",
  "Me diga quais ingredientes você tem!",
  "Está procurando uma receita ou uma dica?",
  "Qual prato você está com vontade de preparar?",
  "Hora de cozinhar! No que posso te ajudar?",
  "Você vai cozinhar só para você ou para mais pessoas?",
  "Alguma restrição alimentar que eu deva saber?",
  "Doce ou salgado — o que você prefere?",
];

export default function WelcomeMessage({ phrases = defaultPhrases, className = "", color = "#000", fontSize = 36 }) {
  const phrase = useMemo(() => {
    const idx = Math.floor(Math.random() * phrases.length);
    return phrases[idx] || "";
  }, [phrases]);

  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '10px' }}>
        <span style={{ fontWeight: 800, fontSize: '56px', color: '#000' }}>CuocoGPT</span>
        <img
          src={cuoco}
          alt="Cuoco"
          style={{ width: '300px', height: '300px', display: 'inline-block', transform: 'translateY(62px)' }}
        />
      </div>
      <p
        className={`text-center font-semibold`}
        style={{ color, fontSize: `${fontSize}px`, lineHeight: 1.2, transform: 'translateY(-30px)' }}
      >
        {phrase}
      </p>
    </div>
  );
}
