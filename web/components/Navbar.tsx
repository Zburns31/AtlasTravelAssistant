"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

interface NavbarProps {
  model?: string;
  onOpenProfile: () => void;
}

export function Navbar({ model = "openai/gpt-4o", onOpenProfile }: NavbarProps) {
  return (
    <nav className="h-12 px-5 flex items-center justify-between border-b border-subtle-ash bg-canvas-white shrink-0">
      <div className="flex items-center gap-2 font-semibold text-deep-black tracking-tight">
        <span aria-hidden className="inline-block w-2 h-2 rounded-full bg-deep-black" />
        <span className="text-[15px]">Atlas</span>
        <span className="text-[12px] font-normal text-midtone-gray ml-1">
          Travel Assistant
        </span>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="font-mono">
          {model}
        </Badge>
        <Button variant="outline" size="sm" onClick={onOpenProfile}>
          Profile
        </Button>
      </div>
    </nav>
  );
}
