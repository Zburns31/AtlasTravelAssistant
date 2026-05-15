"use client";

import { useEffect } from "react";

import { cn } from "@/lib/cn";
import { Button } from "./Button";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  className,
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-rich-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className={cn(
          "w-full max-w-lg max-h-[90vh] flex flex-col bg-canvas-white rounded-[14px] shadow-[var(--shadow-elevated)] border border-subtle-ash overflow-hidden",
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-subtle-ash">
          <h3 className="text-[16px] font-semibold text-deep-black">{title}</h3>
          <Button
            variant="ghost"
            size="sm"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-4 scroll-thin">
          {children}
        </div>
        {footer && (
          <footer className="flex items-center justify-end gap-2 px-4 py-3 border-t border-subtle-ash bg-canvas-white">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
