import type { ReactNode } from "react";

import type { Message } from "./messages";

/** A warning or failure notice. Setup hints appear only on the dev server. */
export function Callout({
  tone,
  icon,
  message,
  children,
}: {
  tone: "warning" | "danger";
  icon: ReactNode;
  message: Message;
  children?: ReactNode;
}) {
  return (
    <div className={`callout callout--${tone}`} role={tone === "danger" ? "alert" : undefined}>
      <h2 className="callout__title">
        {icon}
        {message.title}
      </h2>
      <p className="callout__detail">{message.detail}</p>
      {import.meta.env.DEV && message.devHint ? (
        <p className="callout__dev">{message.devHint}</p>
      ) : null}
      {children}
    </div>
  );
}
