"use client";

import { useState } from "react";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { ItineraryPanel } from "@/components/itinerary/ItineraryPanel";
import { Navbar } from "@/components/Navbar";
import { ProfileModal } from "@/components/profile/ProfileModal";
import { SidebarPanel } from "@/components/sidebar/SidebarPanel";

export default function HomePage() {
  const [profileOpen, setProfileOpen] = useState(false);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Navbar onOpenProfile={() => setProfileOpen(true)} />
      <main className="flex flex-1 min-h-0">
        <ChatPanel />
        <ItineraryPanel />
        <SidebarPanel />
      </main>
      <ProfileModal
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
      />
    </div>
  );
}
