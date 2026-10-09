import { useEffect } from "react";
import { useNavigate } from "react-router";

import type { ModuleLink } from "@/modules";

/** Alt+1..9 and Alt+0 jump between modules so counter staff never need the mouse. */
export function useModuleShortcuts(modules: ModuleLink[]): void {
  const navigate = useNavigate();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey) return;
      const target = modules.find((m) => m.shortcut === event.key);
      if (target) {
        event.preventDefault();
        void navigate(target.path);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [modules, navigate]);
}
