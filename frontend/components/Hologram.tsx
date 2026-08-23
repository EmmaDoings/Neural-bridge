"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useBridgeStore } from "@/lib/store";
import type { PresetName } from "@/lib/types";

const PRESET_ORDER: PresetName[] = [
  "conversation",
  "meditation",
  "creative",
  "gaming",
  "navigation",
  "surgery",
  "idle",
];

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function Hologram() {
  const containerRef = useRef<HTMLDivElement>(null);
  const frame = useBridgeStore((state) => state.frame);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
    camera.position.z = 5;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.domElement.style.touchAction = "none";
    container.appendChild(renderer.domElement);

    const geometry = new THREE.IcosahedronGeometry(1.35, 2);
    const material = new THREE.MeshStandardMaterial({
      color: "#38bdf8",
      emissive: "#38bdf8",
      emissiveIntensity: 1.8,
      metalness: 0.55,
      roughness: 0.24,
      wireframe: true
    });
    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);
    scene.add(new THREE.AmbientLight("#ffffff", 0.6));

    const light = new THREE.PointLight("#67e8f9", 65);
    light.position.set(3, 4, 5);
    scene.add(light);

    let userYaw = 0;
    let userPitch = 0;
    let dragging = false;
    let hovered = false;
    let moved = 0;
    let downTime = 0;
    let burst = 0;
    const pointers = new Map<number, { x: number; y: number }>();
    let pinchDistance = 0;

    const canvas = renderer.domElement;

    const pointerDistance = () => {
      const values = Array.from(pointers.values());
      if (values.length < 2) return 0;
      return Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y);
    };

    const cyclePreset = () => {
      const current = useBridgeStore.getState().preset;
      const next = PRESET_ORDER[(PRESET_ORDER.indexOf(current) + 1) % PRESET_ORDER.length];
      useBridgeStore.getState().setPreset(next);
      burst = 1;
    };

    const onPointerDown = (event: PointerEvent) => {
      dragging = true;
      hovered = true;
      moved = 0;
      downTime = Date.now();
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      try {
        canvas.setPointerCapture(event.pointerId);
      } catch {
        /* ignore */
      }
      if (pointers.size === 2) pinchDistance = pointerDistance();
    };

    const onPointerMove = (event: PointerEvent) => {
      hovered = true;
      const previous = pointers.get(event.pointerId);
      if (!previous) return;

      const dx = event.clientX - previous.x;
      const dy = event.clientY - previous.y;
      moved += Math.abs(dx) + Math.abs(dy);
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

      if (pointers.size === 1 && dragging) {
        userYaw += dx * 0.006;
        userPitch = clamp(userPitch + dy * 0.006, -1.1, 1.1);
      } else if (pointers.size === 2 && dragging) {
        const distance = pointerDistance();
        const delta = pinchDistance - distance;
        camera.position.z = clamp(camera.position.z + delta * 0.015, 3.2, 9);
        pinchDistance = distance;
      }
    };

    const onPointerUp = (event: PointerEvent) => {
      pointers.delete(event.pointerId);
      if (pointers.size === 0) {
        if (moved < 6 && Date.now() - downTime < 400) {
          cyclePreset();
        }
        dragging = false;
      }
    };

    const onPointerLeave = () => {
      hovered = false;
      dragging = false;
      pointers.clear();
    };

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      camera.position.z = clamp(camera.position.z + event.deltaY * 0.002, 3.2, 9);
    };

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerLeave);
    canvas.addEventListener("wheel", onWheel, { passive: false });

    let animationFrame = 0;
    const clock = new THREE.Clock();
    const animate = () => {
      const focus = useBridgeStore.getState().frame?.metrics.focus ?? 0.5;
      const meditation = useBridgeStore.getState().frame?.metrics.meditation ?? 0.5;
      const color = useBridgeStore.getState().frame?.intent.color ?? "#38bdf8";
      const time = clock.getElapsedTime();
      const pulse = 1 + Math.sin(time * 4) * 0.08 * focus;

      burst *= 0.92;
      material.color.set(color);
      material.emissive.set(color);
      material.emissiveIntensity = 1.8 + burst * 1.5 + (hovered ? 0.6 : 0);

      mesh.rotation.x = userPitch + Math.sin(time * 0.4) * 0.1 + meditation * 0.05;
      mesh.rotation.y = userYaw + time * (0.1 + focus * 0.15);
      mesh.scale.setScalar(pulse + focus * 0.45 + burst * 0.35);

      renderer.render(scene, camera);
      animationFrame = window.requestAnimationFrame(animate);
    };

    const resize = () => {
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };

    window.addEventListener("resize", resize);
    animate();

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      canvas.removeEventListener("wheel", onWheel);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className={`relative h-[360px] overflow-hidden rounded-[2rem] border bg-slate-950/70 shadow-2xl md:h-[560px] ${
        frame ? "border-cyan-300/30 shadow-cyan-500/15" : "border-cyan-300/20 shadow-cyan-500/10"
      }`}
      aria-label={`Interactive hologram ${frame?.intent.label ?? "awaiting signal"}`}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(34,211,238,0.16),transparent_45%)]" />
      <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full border border-white/10 bg-slate-950/80 px-4 py-1.5 text-center text-[11px] uppercase tracking-[0.25em] text-slate-300">
        Drag to rotate · Scroll to zoom · Tap to switch mode
      </div>
    </div>
  );
}