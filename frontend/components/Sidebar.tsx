"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ChevronLeft, ChevronRight, Clapperboard } from "lucide-react";
import { NAV } from "@/lib/nav";

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`${collapsed ? "w-16" : "w-64"} shrink-0 flex flex-col border-r border-zinc-800 bg-zinc-900/60 transition-all duration-200`}
    >
      <div className="flex items-center justify-between px-4 h-16 border-b border-zinc-800">
        <div className="flex items-center gap-2 overflow-hidden">
          <Clapperboard className="text-violet-400 shrink-0" size={22} />
          {!collapsed && <span className="font-bold tracking-wide text-white">CLIPFORGE AI</span>}
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-zinc-400 hover:text-white"
          aria-label="Toggle sidebar"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-3">
        {NAV.map((group) => (
          <div key={group.section} className="mb-4">
            {!collapsed && (
              <p className="px-4 pb-1 text-[11px] font-semibold tracking-widest text-zinc-500">
                {group.section}
              </p>
            )}
            {group.items.map(({ label, href, icon: Icon }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  title={label}
                  className={`mx-2 my-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                    active
                      ? "bg-violet-600/20 text-violet-300"
                      : "text-zinc-400 hover:bg-zinc-800 hover:text-white"
                  }`}
                >
                  <Icon size={18} className="shrink-0" />
                  {!collapsed && <span className="truncate">{label}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}