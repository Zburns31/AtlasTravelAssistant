import { TRANSIT_ICON } from "@/lib/categoryStyles";
import { fmtMoney } from "@/lib/format";
import type { TravelSegment } from "@/lib/types";

export function TravelConnector({ segment: s }: { segment: TravelSegment }) {
  const dur = s.duration_minutes ? `${s.duration_minutes} min` : "";
  const cost = s.estimated_cost_usd != null ? ` · ${fmtMoney(s.estimated_cost_usd)}` : "";
  return (
    <div className="pl-6 my-1 text-[12px] text-midtone-gray flex items-center gap-2">
      <span aria-hidden>{TRANSIT_ICON[s.mode]}</span>
      <span>
        {s.from_location} → {s.to_location}
        {dur && ` · ${dur}`}
        {cost}
      </span>
    </div>
  );
}
