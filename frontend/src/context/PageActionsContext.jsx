import { createContext, useContext } from "react";

const PageActionsContext = createContext({ openArticle: () => {} });

export const PageActionsProvider = PageActionsContext.Provider;

export function usePageActions() {
  return useContext(PageActionsContext);
}
