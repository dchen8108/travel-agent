import type { FrontendBootstrap } from "../types";

declare global {
  interface Window {
    __MILEMARK_BOOTSTRAP__?: FrontendBootstrap;
  }
}

export function frontendBootstrap(): FrontendBootstrap {
  return window.__MILEMARK_BOOTSTRAP__ ?? {};
}
