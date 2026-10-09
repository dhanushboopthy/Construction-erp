import type { ModuleLink } from "@/modules";

export function ComingSoonPage({ module }: { module: ModuleLink }) {
  return (
    <section aria-labelledby="module-title">
      <h1 id="module-title">{module.label}</h1>
      <p>{module.purpose}</p>
      <p>
        Built in Milestone {module.milestone}. See docs/ROADMAP.md for the order of work.
      </p>
    </section>
  );
}
