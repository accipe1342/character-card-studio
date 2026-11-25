/**
 * useStudioContext.js — what a studio has open (the label the header and the collapsed tab row show) and its
 * optional header link, both read from helperBus.
 */
import { useSyncExternalStore } from "react";
import { getHeaderLink, getHelperContext, onHeaderLink, onHelperContext } from "./helperBus";

export function useStudioContext(mode) {
  return useSyncExternalStore(onHelperContext, () => getHelperContext(mode));
}

export function useHeaderLink(mode) {
  return useSyncExternalStore(onHeaderLink, () => getHeaderLink(mode));
}
