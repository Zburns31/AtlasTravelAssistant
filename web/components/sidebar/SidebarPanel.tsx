"use client";

import { useChatStore } from "@/lib/store";
import { BudgetTable } from "./BudgetTable";
import { DestinationInfo } from "./DestinationInfo";
import { MapCard } from "./MapCard";
import { StatusBar } from "./StatusBar";
import { TripStats } from "./TripStats";

export function SidebarPanel() {
  const itinerary = useChatStore((s) => s.itinerary);

  return (
    <aside className="flex flex-col w-[320px] shrink-0 border-l border-subtle-ash bg-canvas-white h-full">
      <div className="flex-1 overflow-y-auto scroll-thin">
        {itinerary ? (
          <>
            <div className="p-4 border-b border-subtle-ash">
              <MapCard itinerary={itinerary} />
            </div>
            <DestinationInfo itinerary={itinerary} />
            <BudgetTable itinerary={itinerary} />
            <TripStats itinerary={itinerary} />
          </>
        ) : (
          <div className="p-4 text-[12px] text-midtone-gray">
            Trip details, map, and budget summary will appear here once an
            itinerary is generated.
          </div>
        )}
      </div>
      <StatusBar />
    </aside>
  );
}
