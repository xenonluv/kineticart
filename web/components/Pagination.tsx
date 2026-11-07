"use client";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

// 1 … 4 5 [6] 7 8 … 42 형태의 번호 목록(현재 기준 앞뒤 2개 + 처음/끝)
function pageList(page: number, total: number): (number | "…")[] {
  const set = new Set([1, total, page - 2, page - 1, page, page + 1, page + 2]);
  const nums = [...set].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  nums.forEach((n, i) => {
    if (i > 0 && n - nums[i - 1] > 1) out.push("…");
    out.push(n);
  });
  return out;
}

export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  const btn =
    "grid h-8 min-w-8 place-items-center rounded-md px-2 text-sm transition disabled:opacity-30";
  return (
    <nav aria-label="페이지" className="flex items-center justify-center gap-1 py-6">
      <button
        className={cn(btn, "text-neutral-300 hover:bg-neutral-800")}
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        aria-label="이전 페이지"
      >
        <ChevronLeft size={16} />
      </button>

      {/* 데스크톱: 번호 목록 */}
      <div className="hidden items-center gap-1 sm:flex">
        {pageList(page, totalPages).map((n, i) =>
          n === "…" ? (
            <span key={`e${i}`} className="px-1 text-neutral-600">
              …
            </span>
          ) : (
            <button
              key={n}
              onClick={() => onChange(n)}
              aria-current={n === page ? "page" : undefined}
              className={cn(
                btn,
                n === page
                  ? "bg-neutral-100 font-semibold text-neutral-900"
                  : "text-neutral-300 hover:bg-neutral-800",
              )}
            >
              {n}
            </button>
          ),
        )}
      </div>

      {/* 모바일: 7 / 42 */}
      <span className="px-3 text-sm text-neutral-300 sm:hidden">
        {page} / {totalPages}
      </span>

      <button
        className={cn(btn, "text-neutral-300 hover:bg-neutral-800")}
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        aria-label="다음 페이지"
      >
        <ChevronRight size={16} />
      </button>
    </nav>
  );
}
