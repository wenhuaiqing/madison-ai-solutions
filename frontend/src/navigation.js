// Auto-discovers pages under src/pages/<Section>/<Page>.jsx. The folder name
// becomes the URL slug; MODULE_META fixes the label, icon, group and order.
//
// The groups follow the delivery lifecycle the advertisement describes -
// discovery, design and build, test, and getting people to use it - so
// reading the nav top to bottom reads like one initiative being delivered.

import {
  Activity, Bot, ClipboardCheck, Database, Inbox, LayoutGrid, Milestone, Route, Scale, ShieldAlert, Workflow,
} from "lucide-react";

const PAGE_MODULES = import.meta.glob("./pages/*/*.jsx", { eager: true });

export const MODULE_META = {
  Overview:   { label: "AI roadmap",            icon: Route,          group: "Discover", order: 0 },
  Process:    { label: "Process, today and after", icon: Workflow,    group: "Discover", order: 1 },
  Lakehouse:  { label: "Lakehouse & lineage",   icon: Database,       group: "Build",    order: 2 },
  Exceptions: { label: "Exception queue",       icon: Inbox,          group: "Build",    order: 3 },
  Triage:     { label: "AI triage",             icon: Bot,            group: "Build",    order: 4 },
  SelfServe:  { label: "Self-serve reporting",  icon: LayoutGrid,     group: "Build",    order: 5, slug: "selfserve" },
  Value:      { label: "What it is worth",      icon: Scale,          group: "Prove",    order: 6 },
  Risk:       { label: "AI risk",               icon: ShieldAlert,    group: "Prove",    order: 7 },
  Delivery:   { label: "Delivery log & UAT",    icon: ClipboardCheck, group: "Prove",    order: 8 },
  Operations: { label: "Operations & adoption", icon: Activity,       group: "Run",      order: 9 },
  Brief:      { label: "First 90 days",         icon: Milestone,      group: "Run",      order: 10 },
};

function slugify(value) {
  return value.toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export function getRoutes() {
  const seen = new Map();
  for (const [path, module] of Object.entries(PAGE_MODULES)) {
    const match = path.match(/^\.\/pages\/([^/]+)\/([^/]+)\.jsx$/);
    if (!match || seen.has(match[1])) continue;
    const section = match[1];
    const meta = MODULE_META[section] || { label: section, order: 99, group: "Other" };
    seen.set(section, {
      section,
      label: meta.label,
      icon: meta.icon || null,
      group: meta.group,
      order: meta.order ?? 99,
      to: `/${meta.slug || slugify(section)}`,
      component: module.default,
    });
  }
  return [...seen.values()].sort((a, b) => a.order - b.order);
}
