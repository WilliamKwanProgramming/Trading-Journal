"use client";

import { useState, type ReactNode } from "react";

export function MetricsToggle({ children }: { children: ReactNode }) {
  const [isVisible, setIsVisible] = useState(true);

  return <div className="metrics-toggle">
    <div className="metrics-toggle-bar">
      <span className="metrics-toggle-label">Advanced statistical analysis</span>
      <button
        className="button button-light"
        type="button"
        aria-controls="account-metrics"
        aria-expanded={isVisible}
        onClick={() => setIsVisible((visible) => !visible)}
      >
        {isVisible ? "Hide advanced metrics" : "Show advanced metrics"}
      </button>
    </div>
    {isVisible ? <div id="account-metrics">{children}</div> : null}
  </div>;
}
