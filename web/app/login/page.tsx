"use client";
import { useState } from "react";
import { KeyRound } from "lucide-react";

export default function LoginPage() {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pw || busy) return;
    setBusy(true);
    setErr(false);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: pw }),
      });
      if (res.ok) {
        window.location.href = "/";
      } else {
        setErr(true);
        setBusy(false);
      }
    } catch {
      setErr(true);
      setBusy(false);
    }
  };

  return (
    <main className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-xs">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-full bg-emerald-600/20 text-emerald-500">
            <KeyRound size={22} />
          </div>
          <h1 className="text-lg font-bold">키네틱 아트 스튜디오</h1>
          <p className="mt-1 text-xs text-neutral-500">비밀번호를 입력하세요</p>
        </div>
        <input
          type="password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          autoFocus
          placeholder="비밀번호"
          className="w-full rounded-lg bg-neutral-900 px-4 py-2.5 text-sm ring-1 ring-neutral-800 outline-none focus:ring-emerald-600"
        />
        {err && <p className="mt-2 text-xs text-red-400">비밀번호가 올바르지 않습니다.</p>}
        <button
          type="submit"
          disabled={busy || !pw}
          className="mt-3 w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:bg-neutral-800 disabled:text-neutral-600"
        >
          {busy ? "확인 중…" : "입장"}
        </button>
      </form>
    </main>
  );
}
