import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        outline: "border-border text-foreground",
        low: "border-transparent bg-risk-low/20 text-risk-low",
        medium: "border-transparent bg-risk-medium/20 text-risk-medium",
        high: "border-transparent bg-risk-high/20 text-risk-high",
        critical: "border-transparent bg-risk-critical/20 text-risk-critical",
        positive: "border-transparent bg-risk-low/20 text-risk-low",
        negative: "border-transparent bg-risk-critical/20 text-risk-critical",
        neutral: "border-transparent bg-secondary text-muted-foreground",
        mixed: "border-transparent bg-risk-medium/20 text-risk-medium",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
