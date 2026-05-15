"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Tabs } from "@/components/ui/Tabs";
import { api } from "@/lib/api";
import { useChatStore } from "@/lib/store";
import { AccommodationCard } from "./AccommodationCard";
import { DaySection } from "./DaySection";
import { EmptyState } from "./EmptyState";
import { FlightCard } from "./FlightCard";

const TABS = [
  { id: "itinerary" as const, label: "Itinerary" },
  { id: "explore" as const, label: "Explore" },
  { id: "budget" as const, label: "Budget" },
  { id: "notes" as const, label: "Notes" },
];

export function ItineraryPanel() {
  const itinerary = useChatStore((s) => s.itinerary);
  const sessionId = useChatStore((s) => s.sessionId);
  const activeTab = useChatStore((s) => s.activeTab);
  const setActiveTab = useChatStore((s) => s.setActiveTab);
  const setStatus = useChatStore((s) => s.setStatus);
  const [busy, setBusy] = useState<"save" | "export" | null>(null);

  const handleSave = async () => {
    setBusy("save");
    try {
      const r = await api.saveItinerary(sessionId);
      setStatus("idle", `Saved → ${r.json_path}`);
    } catch (e) {
      setStatus("error", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const handleExport = async () => {
    setBusy("export");
    try {
      const r = await api.exportItinerary(sessionId);
      setStatus("idle", `Exported → ${r.markdown_path}`);
    } catch (e) {
      setStatus("error", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const header = itinerary
    ? `${itinerary.destination.name}, ${itinerary.destination.country} — ${itinerary.days.length} Days`
    : "Itinerary";

  return (
    <section className="flex-1 flex flex-col bg-canvas-white min-w-0 h-full">
      <header className="flex items-center justify-between px-6 py-4 border-b border-subtle-ash">
        <h2 className="text-[18px] font-semibold text-deep-black tracking-[-0.45px]">
          {header}
        </h2>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled>
            Load
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={!itinerary || busy === "export"}
          >
            {busy === "export" ? "Exporting…" : "Export"}
          </Button>
          <Button
            variant="primary"
            size="sm"
            className="px-4"
            onClick={handleSave}
            disabled={!itinerary || busy === "save"}
          >
            {busy === "save" ? "Saving…" : "Save Trip"}
          </Button>
        </div>
      </header>

      <div className="px-6 pt-3">
        <Tabs tabs={TABS} value={activeTab} onChange={setActiveTab} />
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 scroll-thin">
        {!itinerary ? (
          <EmptyState />
        ) : activeTab === "itinerary" ? (
          <>
            {itinerary.flights.length > 0 && (
              <section className="mb-6">
                <h4 className="text-[12px] uppercase tracking-wide text-midtone-gray mb-2">
                  Flights
                </h4>
                <div className="flex gap-3 overflow-x-auto scroll-thin pb-2">
                  {itinerary.flights.map((f, i) => (
                    <FlightCard key={i} flight={f} />
                  ))}
                </div>
              </section>
            )}
            {itinerary.accommodations.length > 0 && (
              <section className="mb-6">
                <h4 className="text-[12px] uppercase tracking-wide text-midtone-gray mb-2">
                  Accommodation
                </h4>
                <div className="flex gap-3 overflow-x-auto scroll-thin pb-2">
                  {itinerary.accommodations.map((a, i) => (
                    <AccommodationCard key={i} accommodation={a} />
                  ))}
                </div>
              </section>
            )}
            {itinerary.days.map((d, i) => (
              <DaySection key={i} day={d} dayNum={i + 1} />
            ))}
          </>
        ) : (
          <div className="text-[13px] text-midtone-gray">
            The <strong>{activeTab}</strong> tab is coming soon.
          </div>
        )}
      </div>
    </section>
  );
}
