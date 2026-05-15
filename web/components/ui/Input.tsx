"use client";

import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full bg-canvas-white text-rich-black placeholder:text-midtone-gray text-[14px] border border-subtle-ash rounded-[10px] px-2.5 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-deep-black/10 focus-visible:border-rich-black",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
