import { useEffect, useRef, useState } from "react";
import type { MemoryGraph } from "../../api/client";

/**
 * Simple deterministic force-directed graph layout.
 *
 * Runs a fixed number of iterations on mount/prop change and returns final
 * node positions. Deterministic (no animation) so it is stable across re-renders.
 */
function useForceLayout(
  nodes: MemoryGraph["nodes"],
  edges: MemoryGraph["edges"],
  width: number,
  height: number,
) {
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});

  useEffect(() => {
    if (nodes.length === 0) return;

    // Initialize positions in a circle
    const pos: Record<string, { x: number; y: number; vx: number; vy: number }> = {};
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.35;

    nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / nodes.length;
      pos[node.id] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
        vx: 0,
        vy: 0,
      };
    });

    // Simple force simulation
    const iterations = 50;
    for (let iter = 0; iter < iterations; iter++) {
      // Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = pos[nodes[i].id];
          const b = pos[nodes[j].id];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 5000 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      }

      // Attraction along edges
      for (const edge of edges) {
        const a = pos[edge.source];
        const b = pos[edge.target];
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 100) * 0.01 * edge.weight;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }

      // Apply velocities with damping
      for (const node of nodes) {
        const p = pos[node.id];
        p.vx *= 0.9;
        p.vy *= 0.9;
        p.x += p.vx;
        p.y += p.vy;
        // Keep within bounds
        p.x = Math.max(50, Math.min(width - 50, p.x));
        p.y = Math.max(50, Math.min(height - 50, p.y));
      }
    }

    // Extract final positions
    const finalPos: Record<string, { x: number; y: number }> = {};
    for (const node of nodes) {
      finalPos[node.id] = { x: pos[node.id].x, y: pos[node.id].y };
    }
    setPositions(finalPos);
  }, [nodes, edges, width, height]);

  return positions;
}

const CATEGORY_COLORS: Record<string, string> = {
  fact: "#10b981",
  preference: "#8b5cf6",
  event: "#f59e0b",
  goal: "#3b82f6",
};

export default function MemoryGraphView({ graph }: { graph: MemoryGraph }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const width = 700;
  const height = 500;

  const positions = useForceLayout(graph.nodes, graph.edges, width, height);

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        width={width}
        height={height}
        className="mx-auto"
        style={{ background: "#111827" }}
      >
        {/* Edges */}
        {graph.edges.map((edge, i) => {
          const source = positions[edge.source];
          const target = positions[edge.target];
          if (!source || !target) return null;
          const isHighlighted = hoveredNode === edge.source || hoveredNode === edge.target;
          return (
            <line
              key={i}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke={isHighlighted ? "#60a5fa" : "#374151"}
              strokeWidth={isHighlighted ? 2 : 1}
              strokeOpacity={isHighlighted ? 0.8 : 0.3}
            />
          );
        })}

        {/* Nodes */}
        {graph.nodes.map((node) => {
          const pos = positions[node.id];
          if (!pos) return null;
          const color = CATEGORY_COLORS[node.category] || "#6b7280";
          const isHovered = hoveredNode === node.id;
          return (
            <g
              key={node.id}
              onMouseEnter={() => setHoveredNode(node.id)}
              onMouseLeave={() => setHoveredNode(null)}
              className="cursor-pointer"
            >
              <circle
                cx={pos.x}
                cy={pos.y}
                r={isHovered ? 12 : 8}
                fill={color}
                stroke={isHovered ? "#fff" : "none"}
                strokeWidth={2}
              />
              {isHovered && (
                <text
                  x={pos.x}
                  y={pos.y - 20}
                  textAnchor="middle"
                  fill="#fff"
                  fontSize={11}
                  className="pointer-events-none"
                >
                  {node.content.slice(0, 30)}
                  {node.content.length > 30 ? "..." : ""}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="absolute top-4 right-4 bg-gray-800/80 rounded-lg p-3 text-xs">
        <div className="font-medium text-gray-300 mb-2">类别</div>
        {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
          <div key={cat} className="flex items-center gap-2 text-gray-400">
            <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            {cat}
          </div>
        ))}
      </div>

      {/* Stats */}
      <div className="absolute bottom-4 left-4 text-xs text-gray-500">
        {graph.nodes.length} 个记忆 · {graph.edges.length} 条关联
      </div>
    </div>
  );
}
