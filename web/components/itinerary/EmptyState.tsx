export function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center px-6">
      <div className="text-display font-semibold text-deep-black tracking-[-2.4px] mb-2">
        ✨
      </div>
      <h3 className="text-[18px] font-semibold text-deep-black">
        Your itinerary will appear here
      </h3>
      <p className="text-[13px] text-midtone-gray mt-2 max-w-sm">
        Start by typing a trip request in the chat — e.g.{" "}
        <em>“Plan a 5-day trip to Kyoto”</em>.
      </p>
    </div>
  );
}
