export function TypingIndicator() {
  return (
    <div className="self-start max-w-[85%] flex flex-col items-start">
      <div className="rounded-[14px] px-3 py-2 bg-ghost-gray text-rich-black text-[13px] flex items-center gap-2">
        <span>Atlas is thinking</span>
        <span className="typing-dots inline-flex gap-0.5">
          <span>·</span>
          <span>·</span>
          <span>·</span>
        </span>
      </div>
    </div>
  );
}
