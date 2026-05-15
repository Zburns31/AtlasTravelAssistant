"use client";

import { useMemo } from "react";
import { Map, Marker } from "react-map-gl/maplibre";

import { CATEGORY_COLOR } from "@/lib/categoryStyles";
import type { Itinerary } from "@/lib/types";

const MAP_STYLE = "https://demotiles.maplibre.org/style.json";

interface Pin {
  lat: number;
  lon: number;
  color: string;
  label?: string;
}

export function MapCard({ itinerary }: { itinerary: Itinerary }) {
  const coords = itinerary.destination.coordinates;

  const pins = useMemo<Pin[]>(() => {
    const list: Pin[] = [];
    if (coords) {
      list.push({
        lat: coords[0],
        lon: coords[1],
        color: "var(--color-callout-red)",
        label: itinerary.destination.name,
      });
    }
    for (const day of itinerary.days) {
      for (const act of day.activities) {
        if (act.coordinates) {
          list.push({
            lat: act.coordinates[0],
            lon: act.coordinates[1],
            color: CATEGORY_COLOR[act.category],
            label: act.title,
          });
        }
      }
    }
    return list;
  }, [coords, itinerary]);

  return (
    <div className="rounded-[14px] overflow-hidden border border-subtle-ash h-[240px] bg-ghost-gray">
      <Map
        initialViewState={{
          latitude: coords?.[0] ?? 0,
          longitude: coords?.[1] ?? 0,
          zoom: coords ? 11 : 1,
        }}
        mapStyle={MAP_STYLE}
        attributionControl={false}
        style={{ width: "100%", height: "100%" }}
      >
        {pins.map((p, i) => (
          <Marker key={i} latitude={p.lat} longitude={p.lon} anchor="bottom">
            <div
              title={p.label}
              className="w-3 h-3 rounded-full border-2 border-canvas-white shadow"
              style={{ backgroundColor: p.color }}
            />
          </Marker>
        ))}
      </Map>
    </div>
  );
}
