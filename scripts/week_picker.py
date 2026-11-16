import json, sys, datetime as dt, os
IDX = r"C:\Users\Stephen\Documents\GitHub\stt_misc\transcripts\sphere_week_by_week\voice_memo_index_2026-11-15.json"
SEL = r"C:\Users\Stephen\Documents\GitHub\stt_misc\transcripts\sphere_week_by_week\selections_2026-11-15.json"
W1 = dt.date(2025, 3, 24)
rows = json.load(open(IDX, encoding="utf-8"))
sel = json.load(open(SEL, encoding="utf-8")) if os.path.exists(SEL) else {}
def wk(n): return [r for r in rows if r["week"] == n]
cmd = sys.argv[1]
if cmd == "show":
    a, b = int(sys.argv[2]), int(sys.argv[3])
    for n in range(a, b + 1):
        rs = wk(n); mon = W1 + dt.timedelta(days=7*(n-1))
        if not rs: print(f"W{n:03d} {mon:%b %d}-{mon+dt.timedelta(days=6):%b %d}: (nothing)"); continue
        print(f"W{n:03d} {mon:%b %d}-{mon+dt.timedelta(days=6):%b %d}: {len(rs)} recordings, {sum(r['min'] for r in rs)/60:.1f} h")
        for i, r in enumerate(rs, 1):
            w = dt.datetime.fromisoformat(r["when"])
            print(f"   {i:2}. {w:%a %m/%d %H:%M} {r['dev']:6} {r['min']:6.1f}m  {r['title']}")
elif cmd == "pick":  # pick N all | pick N 1,3,4 | pick N none
    n = int(sys.argv[2]); spec = sys.argv[3]; rs = wk(n)
    keep = rs if spec == "all" else [] if spec == "none" else [rs[int(i)-1] for i in spec.split(",")]
    sel[f"W{n:03d}"] = [{"file": r["file"], "title": r["title"], "when": r["when"], "dev": r["dev"], "min": r["min"]} for r in keep]
    json.dump(sel, open(SEL, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"W{n:03d}: {len(keep)} of {len(rs)} kept")
