import { fmtMoney, nightsBetween } from "@/lib/format";
import type { Itinerary } from "@/lib/types";

interface Row {
  label: string;
  amount: number;
}

export function BudgetTable({ itinerary }: { itinerary: Itinerary }) {
  const flights = itinerary.flights.reduce(
    (s, f) => s + (f.estimated_cost_usd ?? 0),
    0,
  );
  const lodging = itinerary.accommodations.reduce(
    (s, a) => s + (a.total_cost_usd ?? 0),
    0,
  );
  let food = 0;
  let activity = 0;
  let transport = 0;
  for (const d of itinerary.days) {
    for (const a of d.activities) {
      if (a.estimated_cost_usd == null) continue;
      if (a.category === "food") food += a.estimated_cost_usd;
      else activity += a.estimated_cost_usd;
    }
    for (const s of d.travel_segments) {
      if (s.estimated_cost_usd != null) transport += s.estimated_cost_usd;
    }
  }

  const nights = itinerary.accommodations[0]
    ? nightsBetween(
        itinerary.accommodations[0].check_in,
        itinerary.accommodations[0].check_out,
      )
    : null;

  const rows: Row[] = [
    { label: "✈️ Flights", amount: flights },
    {
      label: nights ? `🏨 ${nights} nights lodging` : "🏨 Lodging",
      amount: lodging,
    },
    { label: "🍜 Food & dining", amount: food },
    { label: "🎟️ Activities & entry", amount: activity },
    { label: "🚃 Transport (local)", amount: transport },
  ];

  const total = rows.reduce((s, r) => s + r.amount, 0);
  const perDay = total / Math.max(1, itinerary.days.length);

  return (
    <div className="px-4 py-3 border-b border-subtle-ash">
      <h4 className="text-[12px] uppercase tracking-wide text-midtone-gray mb-2">
        Budget
      </h4>
      <table className="w-full text-[12px]">
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-subtle-ash/50">
              <td className="py-1.5 text-rich-black">{r.label}</td>
              <td className="py-1.5 text-right text-rich-black font-medium">
                {fmtMoney(r.amount)}
              </td>
            </tr>
          ))}
          <tr>
            <td className="pt-2 text-deep-black font-semibold">Total</td>
            <td className="pt-2 text-right text-deep-black font-semibold">
              {fmtMoney(total)}
            </td>
          </tr>
          <tr>
            <td className="text-midtone-gray text-[11px]">Per day</td>
            <td className="text-right text-midtone-gray text-[11px]">
              {fmtMoney(perDay)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
