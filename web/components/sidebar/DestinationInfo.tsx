import { Badge } from "@/components/ui/Badge";
import type { Itinerary } from "@/lib/types";

export function DestinationInfo({ itinerary }: { itinerary: Itinerary }) {
  const { destination, preferences } = itinerary;
  const coordStr = destination.coordinates
    ? `${destination.coordinates[0].toFixed(4)}°, ${destination.coordinates[1].toFixed(4)}°`
    : null;

  return (
    <div className="px-4 py-3 border-b border-subtle-ash">
      <h4 className="text-[14px] font-semibold text-deep-black">
        {destination.name}, {destination.country}
      </h4>
      {destination.description && (
        <p className="text-[12px] text-midtone-gray mt-1 line-clamp-3">
          {destination.description}
        </p>
      )}
      {coordStr && (
        <p className="text-[11px] text-midtone-gray mt-2 font-mono">
          📍 {coordStr}
        </p>
      )}
      {preferences.interests.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {preferences.interests.slice(0, 6).map((it) => (
            <Badge key={it} variant="outline">
              {it}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
