import React, { useRef, useEffect } from 'react';

interface Node {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface ConstellationAnimationProps {
  isActive: boolean;
}

export const ConstellationAnimation: React.FC<ConstellationAnimationProps> = ({ isActive }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<Node[]>([]);
  const animationRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size to match parent
    const resizeCanvas = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = rect.width;
        canvas.height = rect.height;
      }
    };
    resizeCanvas();

    // Initialize nodes
    const nodeCount = 15;
    const nodes: Node[] = [];
    for (let i = 0; i < nodeCount; i++) {
      nodes.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
      });
    }
    nodesRef.current = nodes;

    // Connection distance threshold
    const connectionDistance = 60;

    const animate = () => {
      if (!isActive) {
        animationRef.current = requestAnimationFrame(animate);
        return;
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Update and draw nodes
      for (const node of nodes) {
        // Update position
        node.x += node.vx;
        node.y += node.vy;

        // Bounce off edges with padding
        if (node.x < 5 || node.x > canvas.width - 5) node.vx *= -1;
        if (node.y < 5 || node.y > canvas.height - 5) node.vy *= -1;

        // Keep in bounds
        node.x = Math.max(5, Math.min(canvas.width - 5, node.x));
        node.y = Math.max(5, Math.min(canvas.height - 5, node.y));
      }

      // Draw connections
      ctx.strokeStyle = 'rgba(100, 116, 139, 0.12)'; // slate-500 with low opacity
      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const distance = Math.sqrt(dx * dx + dy * dy);

          if (distance < connectionDistance) {
            const opacity = (1 - distance / connectionDistance) * 0.15;
            ctx.strokeStyle = `rgba(100, 116, 139, ${opacity})`;
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[j].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.stroke();
          }
        }
      }

      // Draw nodes
      for (const node of nodes) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, 1.5, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(100, 116, 139, 0.3)'; // slate-500
        ctx.fill();
      }

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    // Handle resize
    const handleResize = () => {
      resizeCanvas();
      // Redistribute nodes on resize
      for (const node of nodes) {
        node.x = Math.min(node.x, canvas.width - 5);
        node.y = Math.min(node.y, canvas.height - 5);
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationRef.current);
      window.removeEventListener('resize', handleResize);
    };
  }, [isActive]);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 pointer-events-none transition-opacity duration-300 ${
        isActive ? 'opacity-100' : 'opacity-0'
      }`}
    />
  );
};
