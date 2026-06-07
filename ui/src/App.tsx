// Copyright 2026 Google LLC. Apache-2.0.
import { Board } from "./Board";
import { Phone } from "./Phone";

export function App() {
  // Single bundle serves both surfaces; route by path.
  const isPhone = location.pathname.replace(/\/+$/, "") === "/join";
  return isPhone ? <Phone /> : <Board />;
}
