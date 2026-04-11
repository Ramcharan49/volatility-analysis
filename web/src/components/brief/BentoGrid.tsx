'use client';

import type { ReactNode } from 'react';
import { motion } from 'framer-motion';

interface Props {
  children: ReactNode;
}

// Container orchestrates the entrance stagger of its child tiles.
// delayChildren waits for RegimeMap's own fade-in to finish first.
const containerVariants = {
  hidden: { opacity: 1 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.35,
    },
  },
};

export default function BentoGrid({ children }: Props) {
  return (
    <motion.div
      className="grid grid-cols-2 grid-rows-2 gap-4 h-full min-h-0"
      variants={containerVariants}
      initial="hidden"
      animate="show"
    >
      {children}
    </motion.div>
  );
}
