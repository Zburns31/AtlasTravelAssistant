import type { Itinerary } from "@/lib/types";

export function TripStats({ itinerary }: { itinerary: Itinerary }) {
  const days = itinerary.days.length;
  const activities = itinerary.days.reduce(
    (s, d) => s + d.activities.length,
    0,
  );
  const travelers = itinerary.preferences.traveler_count;

  return (
    <div className="px-4 py-3 border-b border-subtle-ash">
      <h4 className="text-[12px] uppercase tracking-wide text-midtone-gray mb-2">
        Trip
      </h4>
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: "Days", value: days },
          { label: "Activities", value: activities },
          { label: "Travelers", value: travelers },
        ].map((s) => (
          <div
            key={s.label}
            className="bg-ghost-gray rounded-[10px] px-2 py-2 text-center"
          >
            <div className="text-[16px] font-semibold text-deep-black">
              {s.value}
            </div>
            <div className="text-[10px] text-midtone-gray uppercase tracking-wide">
              {s.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
