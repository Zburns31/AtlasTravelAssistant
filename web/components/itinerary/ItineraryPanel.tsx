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

const PLAN_STATUS_COPY = {
  planning: "Atlas is sketching the trip structure.",
  researching: "Atlas is gathering just enough detail to lock the plan in.",
  synthesising: "Atlas is finalizing each trip card one at a time.",
  completed: "Latest planning run complete.",
} as const;

function stepStatusClasses(status: "planned" | "in_progress" | "completed") {
  switch (status) {
    case "completed":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "in_progress":
      return "border-amber-200 bg-amber-50 text-amber-700";
    default:
      return "border-subtle-ash bg-snow text-midtone-gray";
  }
}

function stepStatusLabel(status: "planned" | "in_progress" | "completed") {
  switch (status) {
    case "completed":
      return "Completed";
    case "in_progress":
      return "In progress";
    default:
      return "Planned";
  }
}

export function ItineraryPanel() {
  const itinerary = useChatStore((s) => s.itinerary);
  const incrementalPlan = useChatStore((s) => s.incrementalPlan);
  const status = useChatStore((s) => s.status);
  const sessionId = useChatStore((s) => s.sessionId);
  const activeTab = useChatStore((s) => s.activeTab);
  const setActiveTab = useChatStore((s) => s.setActiveTab);
  const setStatus = useChatStore((s) => s.setStatus);
  const [busy, setBusy] = useState<"save" | "export" | null>(null);

  const showPlan = !itinerary && (incrementalPlan?.steps.length ?? 0) > 0;

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
    : showPlan
      ? "Building your trip"
      : "Itinerary";

  const cardIcon = (kind: "flight" | "accommodation" | "day" | "generic") => {
    switch (kind) {
      case "flight":
        return "✈️";
      case "accommodation":
        return "🏨";
      case "day":
        return "🗓️";
      default:
        return "•";
    }
  };

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
        {showPlan && (
          <section className="mb-6 max-w-4xl rounded-[24px] border border-subtle-ash bg-white p-5 shadow-card">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h3 className="text-[18px] font-semibold text-deep-black">
                  Building your trip
                </h3>
                <p className="mt-1 text-[13px] text-midtone-gray">
                  {PLAN_STATUS_COPY[incrementalPlan?.status ?? "planning"]}
                </p>
              </div>
              <div className="text-right">
                <div className="text-[11px] uppercase tracking-wide text-midtone-gray">
                  {status === "thinking" ? "Live" : "Saved"}
                </div>
                <div className="mt-1 text-[12px] text-deep-black">
                  {incrementalPlan?.steps.length ?? 0} step{incrementalPlan?.steps.length === 1 ? "" : "s"}
                </div>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {incrementalPlan?.steps.map((step) => {
                return (
                  <article
                    key={step.id}
                    className="rounded-[20px] border border-subtle-ash bg-snow px-4 py-4"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-full bg-soft-sand text-[18px]">
                        <span aria-hidden>{cardIcon(step.kind)}</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-[14px] font-medium text-deep-black">
                            {step.task}
                          </div>
                          <span
                            className={`rounded-full border px-2 py-1 text-[11px] font-medium ${stepStatusClasses(step.status)}`}
                          >
                            {stepStatusLabel(step.status)}
                          </span>
                        </div>

                        {step.notes && (
                          <p className="mt-2 text-[12px] text-midtone-gray">
                            {step.notes}
                          </p>
                        )}

                        {step.preview_lines.length > 0 && (
                          <div className="mt-3 space-y-2">
                            {step.preview_lines.map((line, index) => (
                              <div
                                key={`${step.id}-preview-${index}`}
                                className="rounded-[14px] border border-subtle-ash bg-white px-3 py-2 text-[12px] text-deep-black"
                              >
                                {line}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        )}

        {!itinerary ? (
          !showPlan ? (
            <EmptyState />
          ) : (
            <section className="max-w-3xl rounded-[24px] border border-dashed border-subtle-ash bg-white px-5 py-4 text-[13px] text-midtone-gray shadow-card">
              Atlas will lock in flights, stay, and each day card here before the final itinerary takes over.
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
