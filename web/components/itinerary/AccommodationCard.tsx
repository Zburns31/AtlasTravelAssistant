import { Card } from "@/components/ui/Card";
import { fmtDate, fmtMoney, nightsBetween } from "@/lib/format";
import type { Accommodation } from "@/lib/types";

export function AccommodationCard({ accommodation: a }: { accommodation: Accommodation }) {
  const nights = nightsBetween(a.check_in, a.check_out);
  const sub = [
    a.star_rating != null && `${a.star_rating.toFixed(0)}-star`,
    a.location,
    a.description,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Card className="min-w-[260px]">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[18px]" aria-hidden>
          🏨
        </span>
        <span className="text-[14px] font-semibold text-deep-black">
          {fmtMoney(a.total_cost_usd)}
        </span>
      </div>
      <h4 className="text-[16px] font-semibold text-deep-black">{a.name}</h4>
      <p className="text-[12px] text-midtone-gray mt-1 line-clamp-2">{sub}</p>
      <div className="flex flex-col gap-1 mt-3 text-[12px] text-rich-black">
        <span>
          📅 {fmtDate(a.check_in)} – {fmtDate(a.check_out)} ({nights} nights)
        </span>
        {a.nightly_rate_usd != null && (
          <span>💰 {fmtMoney(a.nightly_rate_usd)}/night</span>
        )}
      </div>
    </Card>
  );
}
