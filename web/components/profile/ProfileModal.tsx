"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { useProfile } from "@/hooks/useProfile";
import type { TripPace, UserProfile } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

const PACE_OPTIONS: { value: TripPace; label: string }[] = [
  { value: "relaxed", label: "Relaxed — 2–3 activities/day" },
  { value: "moderate", label: "Moderate — 3–4 activities/day" },
  { value: "packed", label: "Packed — 5+ activities/day" },
];

function TagList({
  values,
  onChange,
  placeholder,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (!v) return;
    if (values.includes(v)) {
      setDraft("");
      return;
    }
    onChange([...values, v]);
    setDraft("");
  };
  return (
    <div>
      <div className="flex flex-wrap gap-1 mb-2 min-h-[24px]">
        {values.map((v) => (
          <Badge key={v} variant="neutral" className="gap-1">
            {v}
            <button
              type="button"
              aria-label={`Remove ${v}`}
              onClick={() => onChange(values.filter((x) => x !== v))}
              className="text-midtone-gray hover:text-deep-black"
            >
              ×
            </button>
          </Badge>
        ))}
      </div>
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={placeholder}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          }
        }}
      />
    </div>
  );
}

export function ProfileModal({ open, onClose }: Props) {
  const { profile, setProfile, save, loading } = useProfile();

  if (!profile) {
    return (
      <Modal open={open} onClose={onClose} title="Travel Preferences">
        <p className="text-[13px] text-midtone-gray">
          {loading ? "Loading…" : "Profile unavailable."}
        </p>
      </Modal>
    );
  }

  const patch = (p: Partial<UserProfile>) =>
    setProfile({ ...profile, ...p });

  const handleSave = async () => {
    try {
      await save(profile);
      onClose();
    } catch {
      /* error surfaced in hook */
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Travel Preferences"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={loading}
            className="px-4"
          >
            {loading ? "Saving…" : "Save Profile"}
          </Button>
        </>
      }
    >
      <div className="grid gap-4 text-[13px]">
        <div className="grid grid-cols-2 gap-3 text-midtone-gray">
          <div>
            Trips saved:{" "}
            <strong className="text-rich-black">{profile.trip_count}</strong>
          </div>
          <div>
            Last updated:{" "}
            <strong className="text-rich-black">
              {new Date(profile.updated_at).toLocaleString()}
            </strong>
          </div>
        </div>

        <div>
          <label className="block text-[12px] font-medium text-deep-black mb-1">
            Favourite Destination Types
          </label>
          <TagList
            values={profile.favourite_destination_types}
            onChange={(v) => patch({ favourite_destination_types: v })}
            placeholder="Add a type (press Enter)…"
          />
        </div>

        <div>
          <label className="block text-[12px] font-medium text-deep-black mb-1">
            Favourite Activity Categories
          </label>
          <TagList
            values={profile.favourite_categories}
            onChange={(v) => patch({ favourite_categories: v })}
            placeholder="Add a category (press Enter)…"
          />
        </div>

        <div>
          <label className="block text-[12px] font-medium text-deep-black mb-1">
            Preferred Pace
          </label>
          <select
            value={profile.preferred_pace}
            onChange={(e) =>
              patch({ preferred_pace: e.target.value as TripPace })
            }
            className="w-full bg-canvas-white text-rich-black text-[14px] border border-subtle-ash rounded-[10px] px-2.5 py-1.5"
          >
            {PACE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[12px] font-medium text-deep-black mb-1">
            Typical Daily Budget (USD)
          </label>
          <Input
            type="number"
            value={profile.typical_budget_usd ?? ""}
            onChange={(e) =>
              patch({
                typical_budget_usd:
                  e.target.value === "" ? null : Number(e.target.value),
              })
            }
            placeholder="150"
          />
        </div>

        {profile.past_destinations.length > 0 && (
          <div>
            <label className="block text-[12px] font-medium text-deep-black mb-1">
              Past Destinations
            </label>
            <div className="flex flex-wrap gap-1">
              {profile.past_destinations.map((d) => (
                <Badge key={d} variant="outline">
                  {d}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
