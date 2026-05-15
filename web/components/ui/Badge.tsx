import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-[26px] px-2 py-0.5 text-[12px] font-medium",
  {
    variants: {
      variant: {
        inverse: "bg-deep-black text-canvas-white",
        neutral: "bg-ghost-gray text-rich-black",
        outline:
          "bg-transparent text-rich-black border border-subtle-ash",
        success:
          "bg-canvas-white text-success-green border border-success-green/30",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, className }))} {...props} />
  );
}
