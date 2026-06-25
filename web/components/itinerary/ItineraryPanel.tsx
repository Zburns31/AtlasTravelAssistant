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
  const taskPlan = useChatStore((s) => s.taskPlan);
  const toolProgress = useChatStore((s) => s.toolProgress);
  const status = useChatStore((s) => s.status);
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
          taskPlan.length === 0 ? (
            <EmptyState />
          ) : (
            <section className="max-w-3xl">
              <div className="mb-6 rounded-[24px] border border-subtle-ash bg-white p-5 shadow-card">
                <div className="flex items-center justify-between gap-4 mb-3">
                  <div>
                    <h3 className="text-[18px] font-semibold text-deep-black">
                      Building your trip plan
                    </h3>
                    <p className="text-[13px] text-midtone-gray mt-1">
                      Atlas is drafting the high-level plan first, then filling it in with research.
                    </p>
                  </div>
                  <span className="text-[11px] uppercase tracking-wide text-midtone-gray">
                    {status === "thinking" ? "In progress" : "Draft"}
                  </span>
                </div>
                <div className="space-y-3">
                  {taskPlan.map((step) => (
                    <div
                      key={step.step}
                      className="rounded-[18px] border border-subtle-ash bg-snow px-4 py-3"
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-soft-sand text-[11px] font-semibold text-deep-black">
                          {step.step}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-[14px] font-medium text-deep-black">
                            {step.task}
                          </div>
                          {step.notes && (
                            <p className="mt-1 text-[12px] text-midtone-gray">
                              {step.notes}
                            </p>
                          )}
                          {step.tools && step.tools.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {step.tools.map((tool) => (
                                <span
                                  key={tool}
                                  className="rounded-full border border-subtle-ash px-2 py-1 text-[11px] text-midtone-gray"
                                >
                                  {tool}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {toolProgress.length > 0 && (
                <section className="rounded-[24px] border border-subtle-ash bg-white p-5 shadow-card">
                  <h4 className="text-[12px] uppercase tracking-wide text-midtone-gray mb-3">
                    Live research
                  </h4>
                  <div className="space-y-3">
                    {toolProgress.slice(-6).map((event, index) => (
                      <div key={`${event.tool}-${index}`} className="text-[13px] text-deep-black">
                        <div className="font-medium">{event.tool ?? "Tool update"}</div>
                        {event.content_preview && (
                          <p className="mt-1 text-midtone-gray">{event.content_preview}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </section>
          )
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
