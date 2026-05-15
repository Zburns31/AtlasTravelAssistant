import { Card } from "@/components/ui/Card";
import { fmtDateTime, fmtMoney } from "@/lib/format";
import type { Flight } from "@/lib/types";

export function FlightCard({ flight: f }: { flight: Flight }) {
  const route = `${f.departure_airport} → ${f.arrival_airport}`;
  const dur = f.duration_hours ? `${Math.round(f.duration_hours)}h` : "";
  const sub = [
    `${f.airline} ${f.flight_number}`,
    f.cabin_class && f.cabin_class[0].toUpperCase() + f.cabin_class.slice(1),
    dur && `${dur} direct`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Card className="min-w-[260px]">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[18px]" aria-hidden>
          ✈️
        </span>
        <span className="text-[14px] font-semibold text-deep-black">
          {fmtMoney(f.estimated_cost_usd)}
        </span>
      </div>
      <h4 className="text-[16px] font-semibold text-deep-black">{route}</h4>
      <p className="text-[12px] text-midtone-gray mt-1">{sub}</p>
      <div className="flex flex-col gap-1 mt-3 text-[12px] text-rich-black">
        <span>📅 {fmtDateTime(f.departure_time)}</span>
        <span>🛬 {fmtDateTime(f.arrival_time)}</span>
      </div>
    </Card>
  );
}
