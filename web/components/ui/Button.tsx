"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-[14px] font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-deep-black focus-visible:ring-offset-2 focus-visible:ring-offset-canvas-white",
  {
    variants: {
      variant: {
        // Primary Action Button — solid black, 10px radius, generous padding
        primary:
          "bg-deep-black text-canvas-white rounded-[10px] px-12 py-2 hover:bg-rich-black",
        // Ghost — pill, transparent
        ghost:
          "bg-transparent text-rich-black rounded-full px-3 py-1 hover:bg-ghost-gray",
        // Outlined button used for tabs / minor actions
        outline:
          "bg-canvas-white text-rich-black rounded-[10px] px-3 py-1.5 border border-subtle-ash hover:bg-ghost-gray",
        // Subtle pill action
        soft:
          "bg-ghost-gray text-rich-black rounded-full px-3 py-1 hover:bg-subtle-ash",
        destructive:
          "bg-callout-red text-canvas-white rounded-[10px] px-4 py-1.5 hover:opacity-90",
      },
      size: {
        sm: "h-7 text-[12px] px-2.5",
        md: "h-9",
        lg: "h-11 text-[14px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { buttonVariants };
