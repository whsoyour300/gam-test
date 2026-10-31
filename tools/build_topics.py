# -*- coding: utf-8 -*-
"""공개 데이터 → 11주제 × 5문항.

**모든 숫자는 raw/ 의 원본에서 계산합니다.** 지어낸 값이 하나도 없어야 합니다.
결과는 앱이 읽는 topics/*.json 과, 사람이 읽는 tools/정답지.md 로 나갑니다.

정답지와 이 스크립트는 .vercelignore 에 들어 있어 **배포되지 않습니다.**
공개 URL 에 정답지가 올라가면 게임이 성립하지 않습니다.

실행 (저장소 최상위에서):
    python tools/build_topics.py
"""
from __future__ import annotations

import csv
import io
import json
import sys
import datetime as dt
from collections import Counter
from pathlib import Path
from statistics import mean

# 윈도우 콘솔(cp949)은 이모지 · 기호를 못 찍고 멈춘다. 출력만 UTF-8 로 맞춘다
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

HERE = Path(__file__).resolve().parent          # tools/
APP = HERE.parent                                # 저장소 최상위 = 배포되는 곳
RAW = APP / "data" / "raw"
OUT = APP / "topics"

TOPICS: list[dict] = []


def load_json(name):
    return json.load(io.open(RAW / name, encoding="utf-8"))


def load_csv(name):
    return list(csv.DictReader(io.open(RAW / name, encoding="utf-8")))


# World Bank·OWID 응답에는 '유럽연합' '고소득국' 같은 **집계치**가 섞여 있다.
# 그대로 순위를 매기면 나라와 대륙을 한 줄에 놓고 세는 셈이 된다.
REAL = {x["id"] for x in load_json("wb_countries.json")[1]
        if x["region"]["id"] != "NA"}


def wb_countries(rows, year):
    """그 해의 실제 국가 값만 남긴다 (집계치 제외)."""
    return {r["country"]["value"]: r["value"] for r in rows
            if int(r["date"]) == year and r["countryiso3code"] in REAL}


def owid_countries(rows, year, col):
    """OWID 도 마찬가지. code 가 비었거나 OWID_ 로 시작하면 집계치다."""
    return {r["entity"]: float(r[col]) for r in rows
            if int(r["year"]) == year and r["code"]
            and not r["code"].startswith("OWID")}


def topic(tid, emoji, title, blurb, source, source_url, questions, caveat=""):
    """caveat = 이 데이터를 믿을 때의 한계. 앱 화면에도 그대로 나간다.

    출처가 다르면 같은 '서울 기온'도 값이 다르다. 그 사실을 감추지 않는다.
    """
    TOPICS.append({"id": tid, "emoji": emoji, "title": title, "blurb": blurb,
                   "source": source, "source_url": source_url,
                   "caveat": caveat, "questions": questions})


def slider(qid, text, answer, unit, lo, hi, step, basis, why):
    return {"id": qid, "type": "slider", "text": text, "unit": unit,
            "min": lo, "max": hi, "step": step,
            "answer": round(float(answer), 1), "basis": basis, "why": why}


def choice(qid, text, options, answer, basis, why):
    assert answer in options, f"{qid}: 정답이 선택지에 없습니다"
    return {"id": qid, "type": "choice", "text": text, "options": options,
            "answer": answer, "basis": basis, "why": why}


def bar_chart(cap, xs, ys, hi=(), ref=None, ref_label="", unit="%", signed=True):
    """결과 화면의 막대 그래프 — 정답인 항목(hi)만 진하게, ref 는 점선.
    signed=True 면 값 앞에 +를 붙인다(상승률). 수준값(원 등)은 False."""
    return {"kind": "bars", "cap": cap, "x": [str(x) for x in xs],
            "y": [round(v, 1) for v in ys], "hi": [str(h) for h in hi],
            "ref": None if ref is None else round(ref, 1), "ref_label": ref_label,
            "unit": unit, "signed": signed}


def line_chart(cap, xs, ys, marks):
    """결과 화면의 선 그래프 — marks = [(x, 글, 'up'|'down', 'above'|'below'), …]"""
    return {"kind": "line", "cap": cap, "x": list(xs), "y": [round(v, 2) for v in ys],
            "marks": [{"x": x, "label": l, "tone": t, "pos": p} for x, l, t, p in marks]}


def write_pack(t):
    """topics/<id>.json 을 쓰고, topics.json 목록에 넣을 한 줄을 돌려준다."""
    pack = {k: t[k] for k in ("id", "emoji", "title", "blurb",
                              "source", "source_url", "caveat")}
    pack["questions"] = t["questions"]
    io.open(OUT / f"{t['id']}.json", "w", encoding="utf-8").write(
        json.dumps(pack, ensure_ascii=False, indent=2))
    return {k: t[k] for k in ("id", "emoji", "title", "blurb", "source")}


# ── 12. DRAM 가격 ────────────────────────────────────────────────
# 한국은행 수출물가지수(품목별) DRAM · 달러기준. DRAM 은 달러로 거래되므로
# 원화기준을 쓰면 환율 변화가 섞인다.
# 세는 방법 — 연 단위(d1·d2·d5)는 ECOS 연간 값(그 해 월평균)을 전년과 비교한다.
#            d4 는 최대 낙폭: 매달을 그때까지의 최고치와 비교한 하락률 중 가장 큰 값.
#            (구간 최고점은 마지막 달이라 '최고점 뒤 최저점'으로 세면 0%가 된다)
def dram():
    rows = load_json("ecos_dram.json")["row"]
    A = {int(r["TIME"]): float(r["DATA_VALUE"]) for r in rows if len(r["TIME"]) == 4}
    M = {r["TIME"][:4] + "-" + r["TIME"][4:]: float(r["DATA_VALUE"])
         for r in rows if len(r["TIME"]) == 6}
    ms = sorted(M)
    # 원본 점검 — 빠진 달이 없고, 연간 값이 그 해 월평균과 같은지
    for a, b in zip(ms, ms[1:]):
        ya, ma = map(int, a.split("-"))
        yb, mb = map(int, b.split("-"))
        assert yb * 12 + mb - (ya * 12 + ma) == 1, f"DRAM 월 누락: {a} → {b}"
    for y, v in A.items():
        vs = [M[k] for k in ms if k.startswith(f"{y}-")]
        if len(vs) == 12:
            assert abs(mean(vs) - v) / v < 0.005, f"DRAM {y} 연간 ≠ 월평균"

    last_y = max(A)                                  # 연간 값이 있는 마지막 해
    yrs = list(range(last_y - 9, last_y + 1))
    yoy = {y: (A[y] / A[y - 1] - 1) * 100 for y in yrs}
    up = max(yoy, key=yoy.get)
    down = min(yoy, key=yoy.get)
    ups = [y for y in yrs if yoy[y] > 0]

    now = ms[-1]
    prev = f"{int(now[:4]) - 3}{now[4:]}"          # 3년 전 같은 달
    r3y = (M[now] / M[prev] - 1) * 100

    win = ms[-120:]
    peak, dd = win[0], (win[0], win[0], 0.0)
    for k in win:
        if M[k] > M[peak]:
            peak = k
        if (M[k] / M[peak] - 1) * 100 < dd[2]:
            dd = (peak, k, (M[k] / M[peak] - 1) * 100)

    def ym(k):
        return f"{k[:4]}년 {int(k[5:])}월"

    # 한계 문장의 숫자도 원본에서 센다 — 바로 앞 달과 값이 같은 달의 수
    flat = sum(1 for a, b in zip(ms, ms[1:]) if M[a] == M[b])

    span = f"{yrs[0]}~{last_y}년"
    idx = "ECOS DRAM 수출물가지수(달러기준, 2020=100)"
    topic(
        "dram", "💾", "DRAM 가격 언제까지 변할까?",
        f"한국은행 DRAM 수출물가지수 {yrs[0]}~{now[:4]}",
        "한국은행 ECOS 수출물가지수(품목별) DRAM · 달러기준 (2020=100)",
        "https://ecos.bok.or.kr/",
        [
            slider("d1", f"최근 10년({span}) 중 DRAM 수출가격이 전년보다 가장 많이 "
                   "오른 해, 상승률은 몇 %였을까요?",
                   yoy[up], "%", 0, 100, 1,
                   f"{span} {idx}의 연평균을 해마다 전년과 비교해 (그 해 ÷ 전년 − 1) × 100 이 "
                   f"가장 큰 해를 골랐고, {up}년 {A[up - 1]:.2f} → {A[up]:.2f} 입니다.",
                   "가격이 크게 오른 해는 뉴스로 기억되지만, 몇 %였는지는 잘 남지 않습니다."),
            slider("d2", "같은 10년 동안 DRAM 수출가격이 가장 크게 떨어진 해, "
                   "하락률은 몇 %였을까요?",
                   -yoy[down], "%", 0, 100, 1,
                   f"{span} {idx}의 연평균을 해마다 전년과 비교해 (그 해 ÷ 전년 − 1) × 100 이 "
                   f"가장 작은 해를 골라 하락 폭을 양수로 적었고, {down}년 "
                   f"{A[down - 1]:.2f} → {A[down]:.2f} 입니다.",
                   "반도체는 오를 때만큼 크게 떨어집니다. 한 해에 절반 가까이 빠지기도 합니다."),
            slider("d3", f"최근 3년({ym(prev)} → {ym(now)}) 동안 DRAM 수출가격은 "
                   "몇 % 올랐을까요?",
                   r3y, "%", 0, 1000, 10,
                   f"{idx}의 {ym(prev)}과 {ym(now)} 월별 값 {M[prev]:.2f} → {M[now]:.2f} 를 "
                   "(나중 ÷ 처음 − 1) × 100 으로 비교했습니다.",
                   "최근 값은 체감보다 훨씬 크게 움직였을 수 있습니다. 최근 몇 달은 "
                   "잠정치라 나중에 고쳐질 수 있습니다."),
            slider("d4", f"최근 10년({ym(win[0])}~{ym(now)}) 월별 지수에서, 고점을 찍은 뒤 "
                   "가장 크게 떨어졌을 때 하락률은 몇 %였을까요?",
                   -dd[2], "%", 0, 100, 1,
                   f"{ym(win[0])}~{ym(now)} {idx} 월별 값 {len(win)}개에서 매달을 그때까지의 "
                   f"최고치와 비교한 하락률 중 가장 큰 값으로, {ym(dd[0])} {M[dd[0]]:.2f} → "
                   f"{ym(dd[1])} {M[dd[1]]:.2f} 입니다.",
                   "연평균으로 보면 가려지는 낙폭이 월별로 보면 드러납니다."),
            slider("d5", f"{span} 10년 가운데, DRAM 수출가격이 전년보다 오른 해는 "
                   "몇 번일까요?",
                   len(ups), "번", 0, 10, 1,
                   f"{span} {idx}의 연평균을 해마다 전년과 비교해 오른 해를 셌고, "
                   f"{', '.join(map(str, ups))}년입니다.",
                   "'반도체는 계속 오른다'는 인상과 달리, 오르고 내리기를 반복합니다."),
        ],
        caveat="이 숫자는 한국은행이 주 지수로 발표하는 원화기준이 아니라 달러기준이고 "
               "여러 규격·업체의 DRAM 계약가격을 묶은 지수이며, 1·2·5번은 한 해 12개월 "
               f"평균으로 셌고, {ms[0][:4]}년 이후 월별 값 중 {flat}번은 앞 달과 같은 값이 "
               "이어지는데 계약이 없거나 자료를 못 받은 달에 직전 가격을 이어 쓴 것일 수 "
               f"있으며, 가장 최근 {ym(now)} 값은 잠정치라 다음 달 발표 때 고쳐질 수 "
               "있습니다.")

    # 결과 화면의 문항별 그래프 — 문항을 센 것과 같은 값을 넣는다
    q = TOPICS[-1]["questions"]
    cap_y = "해마다 전년 대비 상승률(연평균, %)"
    q[0]["chart"] = bar_chart(cap_y, yrs, [yoy[y] for y in yrs], hi=[up])
    q[1]["chart"] = bar_chart(cap_y, yrs, [yoy[y] for y in yrs], hi=[down])
    near = ms[-48:]
    q[2]["chart"] = line_chart("최근 4년 월별 수출물가지수", near, [M[k] for k in near],
                               [(prev, f"3년 전 {ym(prev)}", "up", "above"),
                                (now, f"{ym(now)}", "up", "below")])
    q[3]["chart"] = line_chart("최근 10년 월별 수출물가지수", win, [M[k] for k in win],
                               [(dd[0], f"고점 {ym(dd[0])}", "up", "above"),
                                (dd[1], f"저점 {ym(dd[1])}", "down", "below")])
    q[4]["chart"] = bar_chart(cap_y, yrs, [yoy[y] for y in yrs])

    # 업계 배경 — 계산이 아니라 시장 설명이다. 글에 적은 해가 계산 결과와 어긋나면 멈춘다
    assert (up, down, dd[0][:4], dd[1][:7], prev[:4]) == (2017, 2019, "2018", "2023-08", "2023"), \
        "DRAM 정답 시점이 바뀌었습니다 — 업계 배경 글을 다시 써야 합니다"
    q[0]["insight"] = (f"{up}년은 클라우드 데이터센터의 서버 증설과 스마트폰 메모리 탑재량 증가로 "
                       "수요가 늘었는데, 미세공정 전환이 어려워져 공급이 따라가지 못한 "
                       "'슈퍼사이클'의 첫해였습니다.")
    q[1]["insight"] = (f"호황 때 늘린 생산이 쏟아지던 {down}년, 데이터센터 고객사들이 쌓아 둔 재고를 "
                       "먼저 소진하며 주문을 줄였고(재고 조정) 미·중 무역 갈등까지 겹쳤습니다. "
                       "삼성전자·SK하이닉스·마이크론이 연초부터 투자를 줄였지만 이미 늘어난 공급을 "
                       "되돌리지 못했습니다.")
    q[2]["insight"] = (f"{ym(prev)}은 2023년 감산 직후의 바닥 근처였습니다. 그 뒤 제조사 감산으로 재고가 "
                       "줄어든 데다 AI 데이터센터 수요로 고대역폭메모리(HBM) 생산이 급증했고, HBM은 "
                       "같은 용량에 웨이퍼를 더 많이 써서 일반 DRAM 생산 능력이 줄었습니다. 시장조사업체 "
                       "TrendForce는 2026년 1분기 일반 DRAM 계약가격이 전 분기보다 90~95% 올라 "
                       "분기 기준 사상 최대 상승이 될 것으로 봤습니다.")
    q[3]["insight"] = (f"{ym(dd[0])} 고점 뒤 2019년 재고 조정으로 한 번 꺾였고, 코로나 특수가 끝난 "
                       "2022년부터 PC·스마트폰 수요가 줄고 금리 인상으로 소비가 움츠러들며 다시 "
                       "떨어졌습니다. 2023년 4월 삼성전자가 외환위기 이후 처음으로 감산을 공식화하고 "
                       "SK하이닉스·마이크론도 생산과 투자를 줄인 뒤 "
                       f"{ym(dd[1])}에 바닥을 찍었습니다.")
    q[4]["insight"] = ("DRAM은 소수 업체가 몇 년 단위로 공장을 늘리는 산업이라, 호황 때 늘린 투자가 "
                       "1~2년 뒤 공급 과잉이 되는 '실리콘 사이클'이 반복됩니다. 2017·2018년 서버 호황 → "
                       "2019·2020년 하락 → 2021년 코로나 특수 → 2022·2023년 하락 → 2024·2025년 감산과 "
                       "AI 수요로 회복의 흐름입니다.")


# ── 13. 엔화 ─────────────────────────────────────────────────────
# Frankfurter(ECB) 의 유로 대비 JPY·KRW 로 원/100엔 = KRW ÷ JPY × 100 을 날마다 만든다 (교차환율).
# 세는 방법 — 연평균(j1·j2·j5)은 그 해 ECB 거래일마다의 원/100엔을 평균한다.
#            j5 의 '오른 해'는 원/100엔 숫자가 전년보다 커진 해(엔화 강세)다.
def jpykrw():
    rates = load_json("jpykrw.json")["rates"]
    D = sorted((d, v["KRW"] / v["JPY"] * 100) for d, v in rates.items())
    D = [(d, v) for d, v in D if d <= "2025-12-31"]   # 문항은 모두 2025년까지
    assert D[0][0] == "1999-01-04", "엔화 원본이 1999-01-04 에서 시작하지 않습니다"

    yrs = range(1999, 2026)
    A = {y: mean(v for d, v in D if d[:4] == str(y)) for y in yrs}
    top = max(A, key=A.get)
    yoy = {y: (A[y] / A[y - 1] - 1) * 100 for y in range(2000, 2026)}
    down = min(yoy, key=yoy.get)
    ups = [y for y in range(2016, 2026) if yoy[y] > 0]

    d20 = [x for x in D if x[0][:4] == "2020"][0]
    d25 = [x for x in D if x[0][:4] == "2025"][-1]
    chg = (d25[1] / d20[1] - 1) * 100
    hi_d, hi_v = max(D, key=lambda x: x[1])

    def ymd(d):
        return f"{d[:4]}년 {int(d[5:7])}월 {int(d[8:])}일"

    src = "Frankfurter(ECB 기준환율)의 유로 대비 엔·원 값으로 계산한 원/100엔"
    topic(
        "jpykrw", "💴", "엔화 이렇게 무너지나?",
        "100엔은 몇 원일까, 1999~2025년 매일의 원/100엔",
        "Frankfurter (유럽중앙은행 고시) · 원/100엔 교차환율", "https://frankfurter.dev/",
        [
            slider("j1", "1999~2025년 중 100엔의 연평균 원화 가치가 가장 비쌌던 해, "
                   "얼마였을까요?",
                   A[top], "원", 700, 1700, 10,
                   f"1999~2025년 {src}을 해마다 거래일 평균해 가장 큰 해를 골랐고, "
                   f"{top}년 {A[top]:,.1f}원입니다.",
                   "'100엔 = 1,000원'이라는 기준점이 강해서 엔고 때의 높이를 낮게 잡기 쉽습니다."),
            slider("j2", "2000~2025년 중 엔화의 연평균 원화 가치가 전년보다 가장 크게 "
                   "하락한 해, 몇 % 떨어졌을까요?",
                   -yoy[down], "%", 0, 40, 1,
                   f"2000~2025년 {src}의 거래일 평균을 해마다 전년과 비교해 "
                   f"(그 해 ÷ 전년 − 1) × 100 이 가장 작은 해를 골라 하락 폭을 양수로 적었고, "
                   f"{down}년 {A[down - 1]:,.1f}원 → {A[down]:,.1f}원입니다.",
                   "엔저는 서서히 온 것 같지만, 한 해에 크게 꺾인 때가 있습니다."),
            slider("j3", "2020년 첫 거래일부터 2025년 마지막 거래일까지 100엔의 원화 "
                   "가치는 몇 % 변했을까요?",
                   chg, "%", -60, 60, 1,
                   f"{src}의 2020년 첫 ECB 거래일({ymd(d20[0])}) {d20[1]:,.1f}원과 "
                   f"2025년 마지막 거래일({ymd(d25[0])}) {d25[1]:,.1f}원을 "
                   "(나중 ÷ 처음 − 1) × 100 으로 비교했습니다.",
                   "여행 갈 때마다 '엔화 싸다'는 말을 들었어도, 몇 년 동안 얼마나 빠졌는지는 "
                   "잘 짐작하지 못합니다."),
            slider("j4", "1999~2025년 중 100엔을 가장 비싸게 살 수밖에 없었던 날, "
                   "100엔은 약 몇 원이었을까요?",
                   hi_v, "원", 800, 1800, 10,
                   f"1999~2025년 ECB 거래일 {len(D):,}일의 {src} 중 가장 큰 값으로, "
                   f"{ymd(hi_d)} {hi_v:,.1f}원입니다.",
                   "연평균으로는 가려지는 하루의 꼭짓점은 평균보다 훨씬 높습니다."),
            slider("j5", "2016~2025년 10년 동안 연평균 엔화 환율이 전년보다 오른 해는 "
                   "총 몇 번일까요?",
                   len(ups), "번", 0, 10, 1,
                   f"2016~2025년 {src}의 거래일 평균을 해마다 전년과 비교해 원/100엔이 "
                   f"커진(엔화가 비싸진) 해를 셌고, {', '.join(map(str, ups))}년입니다.",
                   "'엔화는 계속 떨어졌다'는 인상과 달리, 오른 해도 섞여 있습니다."),
        ],
        caveat="이 원/100엔은 은행 고시 환율이 아니라 유럽중앙은행이 하루 한 번(중부유럽 "
               "14:10 무렵, 한국 시간으로는 밤) 정하는 참고용 유로 대비 엔·원 기준환율을 나눠 "
               "만든 값이라 서울 외환시장 마감 환율이나 수수료가 붙는 은행 매입가와 다르고, "
               "날짜도 ECB 영업일 기준이라 3번의 '2025년 마지막 거래일'이 한국 외환시장 "
               f"기준과 다른 {ymd(d25[0])}입니다.")

    # 결과 화면의 문항별 그래프 — 문항을 센 것과 같은 값을 넣는다.
    # 일별 선은 너무 촘촘해 n 거래일마다 하나씩만 그리되, 표시할 날은 꼭 넣는다
    def daily(lo, hi, n, keep):
        pts = [x for x in D if lo <= x[0] <= hi]
        return [x for i, x in enumerate(pts) if i % n == 0 or x[0] in keep or i == len(pts) - 1]

    q = TOPICS[-1]["questions"]
    cap_y = "해마다 전년 대비 변화율(연평균, %)"
    q[0]["chart"] = bar_chart("연평균 원/100엔(원)", yrs, [A[y] for y in yrs], hi=[top],
                              unit="원", signed=False)
    q[1]["chart"] = bar_chart(cap_y, range(2000, 2026), [yoy[y] for y in range(2000, 2026)],
                              hi=[down])
    p3 = daily(d20[0], "2025-12-31", 5, {d20[0], d25[0]})
    q[2]["chart"] = line_chart("2020~2025년 원/100엔(원, 5거래일마다)", [d for d, _ in p3],
                               [v for _, v in p3],
                               [(d20[0], "2020년 첫 거래일", "up", "below-right"),
                                (d25[0], "2025년 마지막 거래일", "down", "above-left")])
    p4 = daily("1999-01-01", "2025-12-31", 10, {hi_d})
    q[3]["chart"] = line_chart("1999~2025년 원/100엔(원, 10거래일마다)", [d for d, _ in p4],
                               [v for _, v in p4], [(hi_d, f"최고 {ymd(hi_d)}", "up", "above")])
    q[4]["chart"] = bar_chart(cap_y, range(2016, 2026), [yoy[y] for y in range(2016, 2026)])

    # 업계 배경 — 계산이 아니라 시장 설명이다. 글에 적은 해가 계산 결과와 어긋나면 멈춘다
    assert (top, down, hi_d[:7], ups) == (2012, 2013, "2009-03", [2016, 2019, 2020, 2025]), \
        "엔화 정답 시점이 바뀌었습니다 — 업계 배경 글을 다시 써야 합니다"
    q[0]["insight"] = ("2008년 금융위기 뒤 세계 투자자들이 안전자산인 엔화로 몰리며 엔고가 이어졌고, "
                       "2011년 동일본 대지진 뒤에는 엔/달러가 75엔대까지 내려가 전후 최고 수준의 "
                       f"엔고가 됐습니다. 그 여파가 남은 {top}년이 연평균으로 가장 비쌌고, "
                       "그해 말 '아베노믹스' 기대가 나오며 흐름이 꺾였습니다.")
    q[1]["insight"] = ("2012년 말 출범한 아베 정부와 2013년 4월 일본은행의 대규모 양적·질적 금융완화로 "
                       f"엔화가 시중에 크게 풀리면서, {down}년 한 해 만에 엔화 가치가 큰 폭으로 "
                       "떨어졌습니다.")
    q[2]["insight"] = ("2022년부터 미국 등 주요국이 물가를 잡으려 금리를 빠르게 올렸지만 일본은행은 "
                       "마이너스 금리를 유지해 금리 차가 크게 벌어졌고, 엔을 빌려 금리가 높은 통화에 "
                       "투자하는 '엔 캐리 트레이드'가 늘며 엔화가 약해졌습니다. 다만 같은 기간 원화도 "
                       "달러에 약해져서, 원/100엔으로 본 하락 폭은 엔/달러로 본 것보다 작습니다.")
    q[3]["insight"] = ("2008년 9월 리먼 브러더스 파산 뒤 위험을 피하려는 돈이 몰려 엔화는 강해진 반면, "
                       "외국인 자금이 빠져나간 원화는 급락해 원/달러가 2009년 3월 초 1,500원대 "
                       "후반까지 올랐습니다. 엔고와 원화 약세가 겹친 그때가 꼭짓점이었습니다.")
    q[4]["insight"] = ("엔화는 세계 경제가 불안할 때 사들이는 안전자산이라 브렉시트 투표(2016년), "
                       "미·중 무역 분쟁(2019년), 코로나19(2020년)처럼 위험이 커진 해에 올랐습니다. "
                       "2025년은 일본은행이 금리를 더 올린 데다 원화가 약세를 보인 영향이 겹쳤습니다.")


# ── 14. 서울 아파트 ──────────────────────────────────────────────
# 한국은행 ECOS 901Y062 KB 주택매매가격지수 아파트(서울) 월간. 가격(원)이 아니라 지수다.
# 세는 방법 — 연 단위(a1·a2·a4)는 12월 값끼리 비교한다(연말 기준, 전년 말 대비).
#            원본이 1986년 1월부터라 1985년 12월이 없다. 그래서 a1 은 1987년부터 센다.
#            a5 는 최대 낙폭: 매달을 그때까지의 최고치와 비교한 하락률 중 가장 큰 값 (DRAM 과 같음).
def seoul_apt():
    rows = load_json("ecos_seoul_apt.json")["row"]
    M = {r["TIME"][:4] + "-" + r["TIME"][4:]: float(r["DATA_VALUE"]) for r in rows}
    ms = sorted(M)
    for a, b in zip(ms, ms[1:]):
        ya, ma = map(int, a.split("-"))
        yb, mb = map(int, b.split("-"))
        assert yb * 12 + mb - (ya * 12 + ma) == 1, f"서울 아파트 월 누락: {a} → {b}"
    base = {r["UNIT_NAME"] for r in rows}
    assert len(base) == 1, f"서울 아파트 지수 기준이 섞여 있습니다: {base}"
    base = base.pop()

    first_y = int(ms[0][:4]) + (ms[0][5:] != "01")   # 1월부터 있는 첫 해
    dec = {y: M[f"{y}-12"] for y in range(first_y, 2026)}
    yoy = {y: (dec[y] / dec[y - 1] - 1) * 100 for y in range(first_y + 1, 2026)}
    # 1번 — 2010~2025년 해마다의 12월끼리 상승률을 단순 평균(떨어진 해는 마이너스로 들어간다)
    y10 = [yoy[y] for y in range(2010, 2026)]
    avg10 = sum(y10) / len(y10)
    y00 = {y: v for y, v in yoy.items() if y >= 2000}
    down = min(y00, key=y00.get)
    ups = [y for y in y00 if y00[y] > 0]
    # 3번 — 2026년은 10월까지만 있어 빼고, 2000~2025년에서 12월끼리 상승률이 가장 큰 해
    top = max(y00, key=y00.get)
    picks = sorted(sorted(y00, key=y00.get, reverse=True)[:4])   # 상승률 상위 4개 해를 보기로

    win = [k for k in ms if "2015-01" <= k <= "2025-12"]
    peak, dd = win[0], (win[0], win[0], 0.0)
    for k in win:
        if M[k] > M[peak]:
            peak = k
        if (M[k] / M[peak] - 1) * 100 < dd[2]:
            dd = (peak, k, (M[k] / M[peak] - 1) * 100)

    def ym(k):
        return f"{k[:4]}년 {int(k[5:])}월"

    # 한계 문장의 숫자도 원본에서 센다 — 바로 앞 달과 값이 같은 달
    flat = [b for a, b in zip(ms, ms[1:]) if M[a] == M[b]]

    idx = f"KB 주택매매가격지수 아파트(서울)({base})"
    topic(
        "seoul-apt", "🏢", "서울 집은 언제까지 비싸질까?",
        f"KB 서울 아파트 매매가격지수 {ms[0][:4]}~2025",
        f"한국은행 ECOS 901Y062 · KB 주택매매가격지수 아파트(서울) ({base})",
        "https://ecos.bok.or.kr/",
        [
            slider("a1", "2010년부터 2025년 12월까지 서울 아파트 매매가격지수의 평균 상승률은 "
                   "몇 %일까요?",
                   avg10, "%", -5, 20, 0.5,
                   f"2010~2025년 {len(y10)}개 해마다 {idx}의 12월 값을 전년 12월과 비교한 "
                   f"(그 해 ÷ 전년 − 1) × 100 을 더해 {len(y10)}으로 나눈 단순 평균이고, "
                   f"떨어진 해는 마이너스로 들어갔습니다(2009년 12월 {dec[2009]:.3f} → "
                   f"2025년 12월 {dec[2025]:.3f}).",
                   "크게 오른 몇 해가 기억에 남아서, 떨어지거나 제자리였던 해까지 넣은 평균은 "
                   "생각보다 낮을 수 있습니다."),
            slider("a2", "2000~2025년 중 서울 아파트 매매가격지수가 전년 말보다 가장 많이 "
                   "떨어진 해, 하락률은 몇 %였을까요?",
                   -y00[down], "%", 0, 30, 0.5,
                   f"2000~2025년 {idx}의 12월 값을 해마다 전년 12월과 비교해 "
                   f"(그 해 ÷ 전년 − 1) × 100 이 가장 작은 해를 골라 하락 폭을 양수로 적었고, "
                   f"{down}년 {dec[down - 1]:.3f} → {dec[down]:.3f} 입니다.",
                   "'폭락'이라는 말이 돌던 해도 연말끼리 비교하면 낙폭은 생각보다 작을 수 있습니다."),
            choice("a3", "2000~2025년 중 서울 아파트 매매 가격이 가장 많이 오른 해는 "
                   "몇 년도일까요?",
                   [f"{y}년" for y in picks], f"{top}년",
                   f"2000~2025년 {idx}의 12월 값을 해마다 전년 12월과 비교해 "
                   f"(그 해 ÷ 전년 − 1) × 100 이 가장 큰 해를 골랐고(2026년은 10월까지만 있어 "
                   f"뺐습니다), 보기는 상승률이 높은 네 해로 "
                   + " · ".join(f"{y}년 {y00[y]:.1f}%" for y in picks) + " 입니다.",
                   "뉴스에 '폭등'이 가장 많이 나온 해와 연말끼리 비교해 가장 많이 오른 해는 "
                   "다를 수 있습니다."),
            slider("a4", "2000~2025년 사이 서울 아파트 가격이 상승한 해는 총 몇 번일까요?",
                   len(ups), "번", 0, 26, 1,
                   f"2000~2025년 {len(y00)}개 해에서 {idx}의 12월 값이 전년 12월보다 커진 해를 "
                   f"셌고, 오르지 않은 해는 "
                   f"{', '.join(str(y) for y in y00 if y not in ups)}년입니다.",
                   "'집값은 매년 오른다'는 인상과 달리, 떨어진 해가 몇 번씩 이어진 때가 있습니다."),
            slider("a5", "2015년 1월부터 2025년 12월까지 고점 대비 서울 아파트 가격이 최대로 "
                   "하락한 수준은 몇 %일까요?",
                   -dd[2], "%", 0, 40, 0.5,
                   f"2015년 1월~2025년 12월 {idx} 월별 값 {len(win)}개에서 매달을 그때까지의 "
                   f"최고치와 비교한 하락률 중 가장 큰 값으로, {ym(dd[0])} {M[dd[0]]:.3f} → "
                   f"{ym(dd[1])} {M[dd[1]]:.3f} 입니다.",
                   "연말끼리 비교하면 가려지는 중간의 낙폭이 월별로 보면 드러납니다."),
        ],
        caveat=f"이 숫자는 실거래 가격이 아니라 KB가 서울 표본 아파트의 시세를 묶은 지수({base})로, "
               "표본이 거래되지 않은 달에는 중개업소가 입력한 시세를 쓰기 때문에 한국부동산원 "
               "실거래가격지수나 뉴스의 실거래 평균가와 오르내린 폭이 다를 수 있고, 1·2·3·4번은 "
               "한 해 평균이 아니라 12월 값끼리 비교했으며, "
               f"{flat[0][:4]}~{flat[-1][:4]}년에는 앞 달과 같은 값이 이어진 달이 {len(flat)}번 "
               "있어 이른 시기의 값은 조사가 거칠었거나 직전 시세를 이어 쓴 것일 수 있습니다.")

    # 결과 화면의 문항별 그래프 — 문항을 센 것과 같은 값을 넣는다
    def bars(years, hi=(), ref=None, ref_label=""):
        return {"kind": "bars", "cap": "해마다 전년 12월 대비 상승률(%)",
                "x": [str(y) for y in years], "y": [round(yoy[y], 1) for y in years],
                "hi": [str(y) for y in hi], "ref": ref and round(ref, 1), "ref_label": ref_label}

    q = TOPICS[-1]["questions"]
    q[0]["chart"] = bars(range(2010, 2026), ref=avg10, ref_label=f"평균 {avg10:.1f}%")
    q[1]["chart"] = bars(y00, hi=[down])
    q[2]["chart"] = bars(y00, hi=[top])
    q[3]["chart"] = bars(y00)
    q[4]["chart"] = {"kind": "line", "cap": "월별 매매가격지수",
                     "x": win, "y": [round(M[k], 2) for k in win],
                     "marks": [{"x": dd[0], "label": f"고점 {ym(dd[0])}"},
                               {"x": dd[1], "label": f"저점 {ym(dd[1])}"}]}


# ── 한 주제만 다시 쓰기 ──────────────────────────────────────────
#   python tools/build_topics.py --only dram
# 다른 주제는 계산하지 않는다. topics/<id>.json 과 topics.json 목록의 그 줄만 바꾼다.
# (정답지.md 는 전체를 돌릴 때만 갱신된다)
ONLY = {"dram": dram, "jpykrw": jpykrw, "seoul-apt": seoul_apt}
if "--only" in sys.argv:
    tid = sys.argv[sys.argv.index("--only") + 1]
    ONLY[tid]()
    t = TOPICS[-1]
    assert len(t["questions"]) == 5, f"{tid}: 문항이 5개가 아닙니다"
    OUT.mkdir(parents=True, exist_ok=True)
    line = write_pack(t)
    idx_path = APP / "topics.json"
    index = json.load(io.open(idx_path, encoding="utf-8"))
    ids = [x["id"] for x in index["topics"]]
    if tid in ids:
        index["topics"][ids.index(tid)] = line
    else:
        index["topics"].append(line)
    io.open(idx_path, "w", encoding="utf-8").write(
        json.dumps(index, ensure_ascii=False, indent=2))
    for q in t["questions"]:
        print(f"{q['id']}  {q['answer']}{q.get('unit', '')}  | {q['text']}\n    근거: {q['basis']}")
    sys.exit(0)


# ════════════════════════════════════════════════════════════════
# 기상 공통
# ════════════════════════════════════════════════════════════════
w = load_json("seoul_weather.json")["daily"]
W = [{"d": dt.date.fromisoformat(t), "hi": hi, "lo": lo, "rain": r}
     for t, hi, lo, r in zip(w["time"], w["temperature_2m_max"],
                             w["temperature_2m_min"], w["precipitation_sum"])]
W24 = [x for x in W if x["d"].year == 2024]


def years(a, b):
    return [x for x in W if a <= x["d"].year <= b]


# ── 1. 서울 기온 ─────────────────────────────────────────────────
# ERA5 는 1950~70년대 구간의 품질이 낮고(초기 확장), 격자 평균이라 도심
# 관측값보다 낮게 나온다. 그래서 '역대 최고기온'이나 '폭염일 추세'처럼
# 그 구간에 기대는 문항은 쓰지 않는다. 열대야·연평균처럼 신호가 뚜렷한 것만 쓴다.
tropical_24 = sum(1 for x in W24 if x["lo"] >= 25)
trop_50s = sum(1 for x in years(1950, 1959) if x["lo"] >= 25) / 10
trop_10s = sum(1 for x in years(2015, 2024) if x["lo"] >= 25) / 10
t_ratio = trop_10s / trop_50s if trop_50s else 0
mean_50s = mean((x["hi"] + x["lo"]) / 2 for x in years(1950, 1959))
mean_10s = mean((x["hi"] + x["lo"]) / 2 for x in years(2015, 2024))
warming = mean_10s - mean_50s
below0_24 = sum(1 for x in W24 if x["lo"] < 0)
hot_days = Counter((x["d"].month, x["d"].day)
                   for x in years(1995, 2024) if x["hi"] >= 33)
peak_day = hot_days.most_common(1)[0]
# 한계 문장의 숫자도 손으로 적지 않는다 — 원본에서 가장 더웠던 날을 찾는다
hottest = max(W, key=lambda x: x["hi"])

topic(
    "seoul-heat", "🌡️", "서울은 얼마나 더워졌나",
    "1950년부터 2024년까지, 서울의 매일 기온",
    "Open-Meteo Archive (ERA5 재분석)", "https://open-meteo.com/",
    [
        slider("h1", "2024년 서울에서 열대야(밤 최저기온 25도 이상)는 며칠이었을까요?",
               tropical_24, "일", 0, 60, 1,
               f"2024년 일최저기온 25도 이상인 날 {tropical_24}일",
               "유난히 더웠던 밤 몇 번이 기억을 지배합니다. 실제 일수는 세어 봐야 "
               "압니다."),
        # 보기는 배수에 가장 가까운 것이 정답이 되게 경계를 둔다 (2.8배 → «약 3배»)
        choice("h2", "1950년대와 2015~2024년, 열대야는 몇 배 차이일까요?",
               ["거의 같다", "약 2배", "약 3배", "약 5배"],
               ["거의 같다", "약 2배", "약 3배", "약 5배"][
                   0 if t_ratio < 1.5 else 1 if t_ratio < 2.5
                   else 2 if t_ratio < 4 else 3],
               f"연평균 열대야 1950년대 {trop_50s:.1f}일 → 2015~2024년 "
               f"{trop_10s:.1f}일 ({t_ratio:.1f}배)",
               "'옛날에도 더웠다'는 느낌과 기록은 다릅니다. 기억은 유난히 더웠던 "
               "몇 밤으로 남지만, 기록은 해마다 빠짐없이 셉니다."),
        slider("h3", "1950년대와 비교해 서울의 연평균 기온은 몇 도 올랐을까요?",
               warming, "도", 0, 4, 0.1,
               f"1950년대 {mean_50s:.2f}도 → 2015~2024년 {mean_10s:.2f}도 "
               f"(+{warming:.2f}도)",
               "1~2도는 작아 보이지만, 그 변화가 열대야 일수를 몇 배로 바꿉니다. "
               "평균의 변화와 극단의 변화는 크기가 다릅니다."),
        choice("h4", "최근 30년간 33도 이상인 날이 가장 잦았던 날짜는?",
               ["7월 초", "7월 말", "8월 초", "8월 말"],
               "7월 말" if peak_day[0][0] == 7 and peak_day[0][1] >= 20
               else "8월 초" if peak_day[0][0] == 8 and peak_day[0][1] <= 10
               else "7월 초" if peak_day[0][0] == 7 else "8월 말",
               f"1995~2024년 중 가장 잦았던 날짜는 {peak_day[0][0]}월 "
               f"{peak_day[0][1]}일 ({peak_day[1]}회)",
               "장마가 끝나는 시점과 가장 더운 시점은 다릅니다."),
        slider("h5", "2024년 서울에서 밤 기온이 영하로 내려간 날은 며칠이었을까요?",
               below0_24, "일", 30, 150, 5,
               f"2024년 일최저기온 0도 미만인 날 {below0_24}일",
               "겨울이 짧아졌다고 느끼지만, 영하로 내려가는 날은 여전히 석 달 "
               "치가 넘습니다."),
    ],
    caveat="ERA5는 넓은 격자의 재분석 값이라 도심 관측소와 다르게 나옵니다. "
           f"예컨대 여기서는 역대 최고기온이 {hottest['hi']:.1f}도"
           f"({hottest['d']:%Y년})지만 기상청 서울 관측 기록은 2018년 39.6도입니다. "
           "같은 '서울 기온'도 출처에 따라 다릅니다.")

# ── 2. 비 ────────────────────────────────────────────────────────
rain_days = [sum(1 for x in W if x["d"].year == y and x["rain"] >= 1.0)
             for y in range(1995, 2025)]
rain_avg = mean(rain_days)
by_month = {m: mean([sum(x["rain"] for x in W
                         if x["d"].year == y and x["d"].month == m)
                     for y in range(1995, 2025)]) for m in range(1, 13)}
wettest_m = max(by_month, key=by_month.get)
max_day = max(W, key=lambda x: x["rain"])
ann = {y: sum(x["rain"] for x in W if x["d"].year == y) for y in range(1995, 2025)}
norm = mean(ann.values())
r2024 = ann[2024]


def days_to_half(y):
    v = sorted((x["rain"] for x in W if x["d"].year == y), reverse=True)
    half, s = sum(v) / 2, 0
    for i, r in enumerate(v, 1):
        s += r
        if s >= half:
            return i
    return len(v)


half_days = round(mean(days_to_half(y) for y in range(1995, 2025)))

topic(
    "seoul-rain", "☔", "비는 언제, 얼마나",
    "서울의 하루치 강수량 30년",
    "Open-Meteo Archive (ERA5 재분석)", "https://open-meteo.com/",
    [
        slider("r1", "서울에서 1년 중 비가 온 날(1mm 이상)은 며칠쯤일까요?",
               rain_avg, "일", 40, 160, 5,
               f"1995~2024년 평균 {rain_avg:.1f}일 "
               f"(최소 {min(rain_days)}일 · 최대 {max(rain_days)}일)",
               "비 오는 날은 기억에 오래 남아서 실제보다 많게 느껴집니다."),
        choice("r2", "1년 강수량이 가장 많은 달은?",
               ["6월", "7월", "8월", "9월"], f"{wettest_m}월",
               " · ".join(f"{m}월 {by_month[m]:.0f}mm" for m in (6, 7, 8, 9)),
               "장마가 낀 달과 비가 가장 많이 오는 달이 같지 않을 수 있습니다."),
        slider("r3", "하루에 내린 비의 최대 기록은?",
               max_day["rain"], "mm", 100, 500, 10,
               f"{max_day['d']:%Y년 %m월 %d일} {max_day['rain']:.1f}mm",
               f"가장 많이 온 날 하루에, 비가 가장 많은 {wettest_m}월 한 달 평균"
               f"({by_month[wettest_m]:.0f}mm)의 {max_day['rain'] / by_month[wettest_m] * 100:.0f}%가 "
               "쏟아졌습니다. 비는 고르게 오지 않습니다."),
        slider("r4", "1년 강수량의 절반은 '비 온 날' 며칠 만에 채워질까요?",
               half_days, "일", 3, 40, 1,
               f"많이 온 날부터 더해서 연 강수량의 절반에 도달하는 데 "
               f"평균 {half_days}일 (1995~2024년)",
               "비는 고르게 오지 않습니다. 열흘 남짓이 1년의 절반을 만듭니다."),
        slider("r5", "2024년 서울 강수량은 30년 평균의 몇 %였을까요?",
               r2024 / norm * 100, "%", 50, 180, 5,
               f"2024년 {r2024:.0f}mm · 1995~2024년 평균 {norm:.0f}mm",
               "'올해 비가 많았다'는 체감과 실제 총량은 자주 어긋납니다."),
    ],
    caveat="ERA5 재분석 값입니다. 기상청 관측 강수량과 조금씩 다릅니다.")

# ── 3. 눈 ─────────────────────────────────────────────────────────
s = load_json("seoul_snowfall.json")["daily"]
S = [{"d": dt.date.fromisoformat(t), "snow": snow}
     for t, snow in zip(s["time"], s["snowfall_sum"])]
snow_years = range(1990, 2025)
snow_days = Counter(x["d"].year for x in S if x["snow"] > 0)
snow_days_per_year = [snow_days.get(y, 0) for y in snow_years]
snow_avg = mean(snow_days_per_year)
snow_avg_90s = mean(snow_days.get(y, 0) for y in range(1990, 2000))
snow_avg_recent = mean(snow_days.get(y, 0) for y in range(2015, 2025))
snow_ratio = snow_avg_recent / snow_avg_90s if snow_avg_90s else 0
snow_max = max(S, key=lambda x: x["snow"])
first_snow = {}
for y in snow_years:
    snowy_days = [x for x in S if x["d"].year == y and x["snow"] > 0]
    if snowy_days:
        first_snow[y] = min(snowy_days, key=lambda x: x["d"])
first_snow_months = Counter(x["d"].month for x in first_snow.values())
first_snow_month, first_snow_month_count = first_snow_months.most_common(1)[0]
snow_month_avg = {
    m: mean([sum(x["snow"] for x in S
                 if x["d"].year == y and x["d"].month == m)
             for y in snow_years])
    for m in range(1, 13)
}
snowiest_month = max(snow_month_avg, key=snow_month_avg.get)

topic(
    "seoul-snow", "❄️", "서울에는 눈이 얼마나 올까",
    "서울의 하루 강설량 1990~2024",
    "Open-Meteo Archive (ERA5 재분석)", "https://open-meteo.com/",
    [
        slider("s1", "1990~2024년, 서울에서 한 해에 눈이 온 날은 평균 며칠일까요?",
               snow_avg, "일", 0, 40, 0.1,
               f"1990~2024년 35개 달력연도에서 일 강설량이 0cm를 초과한 날을 "
               f"연도별로 세어 평균 {snow_avg:.1f}일",
               "눈이 많이 쌓인 날만큼이나, 눈이 내린 날을 세면 겨울의 인상이 달라집니다."),
        slider("s2", "1990년대와 2015~2024년, 한 해 눈 온 날은 몇 배 차이일까요?",
               snow_ratio, "배", 0, 2, 0.1,
               f"1990~1999년 평균 {snow_avg_90s:.1f}일 → "
               f"2015~2024년 평균 {snow_avg_recent:.1f}일 (일 강설량 0cm 초과 기준); 최근 평균을 "
               f"1990년대 평균으로 나눔 ({snow_ratio:.2f}배)",
               "눈 온 날의 변화는 눈이 내린 양의 변화와 다를 수 있습니다."),
        slider("s3", "1990~2024년, 서울에서 하루에 가장 많이 내린 눈은 몇 cm일까요?",
               snow_max["snow"], "cm", 0, 30, 0.1,
               f"1990~2024년 일 강설량(snowfall_sum)의 최댓값은 "
               f"{snow_max['snow']:.1f}cm ({snow_max['d']:%Y년 %m월 %d일})",
               "한 번의 큰 눈이 평소의 강설량을 대표하지는 않습니다."),
        choice("s4", "1990~2024년, 서울의 첫눈은 보통 몇 월에 올까요?",
               ["11월", "12월", "1월", "2월"], f"{first_snow_month}월",
               f"1990~2024년 각 달력연도에서 일 강설량이 0cm를 처음 초과한 날의 달을 세어 "
               f"최빈월 {first_snow_month}월 ({first_snow_month_count}회)",
               "첫눈의 달은 달력연도마다 다를 수 있어, 가장 자주 나온 달로 나타냈습니다."),
        choice("s5", "서울에서 눈이 가장 많이 내리는 달은 언제일까요?",
               ["11월", "12월", "1월", "2월"], f"{snowiest_month}월",
               f"1990~2024년 각 달의 일 강설량을 연도별로 합산해 35년 평균을 내고 "
               f"비교했습니다 ({snowiest_month}월 평균 "
               f"{snow_month_avg[snowiest_month]:.1f}cm/년)",
               "한 달의 강설량은 눈 온 날 수뿐 아니라 하루에 내린 양에도 좌우됩니다."),
    ],
    caveat="ERA5 재분석 격자의 강설량이므로 서울 도심 관측소의 실제 적설·강설량과 다를 수 있습니다.")

# ── 4. 미세먼지 ──────────────────────────────────────────────────
a = load_json("seoul_air.json")["hourly"]
A = [{"t": dt.datetime.fromisoformat(t), "pm25": p25, "pm10": p10}
     for t, p25, p10 in zip(a["time"], a["pm2_5"], a["pm10"])]
A24 = [x for x in A if x["t"].year == 2024]
pm_month = {m: mean([x["pm25"] for x in A if x["t"].month == m])
            for m in range(1, 13)}
worst_m = max(pm_month, key=pm_month.get)
pm_hour = {h: mean([x["pm25"] for x in A if x["t"].hour == h])
           for h in range(24)}
worst_h = max(pm_hour, key=pm_hour.get)
pm24_avg = mean(x["pm25"] for x in A24)


def daily_avg(year):
    d = {}
    for x in A:
        if x["t"].year == year:
            d.setdefault(x["t"].date(), []).append(x["pm25"])
    return {k: mean(v) for k, v in d.items()}


d24 = daily_avg(2024)
d23 = daily_avg(2023)
bad_ratio = sum(1 for v in d24.values() if v > 35) / len(d24) * 100
worse_year = "2023년" if mean(d23.values()) > mean(d24.values()) else "2024년"

topic(
    "seoul-air", "😷", "미세먼지, 언제 나쁜가",
    "서울의 시간별 초미세먼지 2년치",
    "Open-Meteo Air Quality (CAMS)", "https://open-meteo.com/",
    [
        choice("a1", "초미세먼지(PM2.5)가 가장 나쁜 달은?",
               ["1월", "3월", "5월", "11월"],
               f"{worst_m}월" if f"{worst_m}월" in ["1월", "3월", "5월", "11월"]
               else "3월",
               " · ".join(f"{m}월 {pm_month[m]:.1f}" for m in (1, 3, 5, 11))
               + f" (최악은 {worst_m}월 {pm_month[worst_m]:.1f})",
               "황사 뉴스가 많은 달과 실제 수치가 높은 달은 다를 수 있습니다."),
        slider("a2", "2024년 서울의 초미세먼지 연평균 농도는?",
               pm24_avg, "㎍/㎥", 5, 60, 1,
               f"2024년 시간값 {len(A24):,}개의 평균 {pm24_avg:.1f}㎍/㎥ "
               f"(WHO 권고 연평균 5, 국내 기준 15)",
               "'나쁨'인 날이 인상에 남아서 연평균을 높게 잡게 됩니다."),
        choice("a3", "하루 중 초미세먼지가 가장 높은 시간대는?",
               ["새벽 4시", "오전 10시", "오후 3시", "밤 9시"],
               {4: "새벽 4시", 10: "오전 10시", 15: "오후 3시",
                21: "밤 9시"}.get(worst_h, "오전 10시"),
               " · ".join(f"{h}시 {pm_hour[h]:.1f}" for h in (4, 10, 15, 21))
               + f" (최고는 {worst_h}시)",
               "출퇴근 시간이 가장 나쁠 것 같지만 대기가 정체되는 시간은 따로 "
               "있습니다."),
        slider("a4", "2024년 하루 평균이 '나쁨'(35㎍/㎥ 초과)이었던 날의 비율은?",
               bad_ratio, "%", 0, 60, 1,
               f"2024년 {len(d24)}일 중 "
               f"{sum(1 for v in d24.values() if v > 35)}일",
               "마스크를 챙긴 날은 강하게 기억되지만, 1년 전체로 보면 비율이 "
               "다릅니다."),
        choice("a5", "2023년과 2024년 중 초미세먼지가 더 나빴던 해는?",
               ["2023년", "2024년"], worse_year,
               f"연평균 2023년 {mean(d23.values()):.1f} · "
               f"2024년 {mean(d24.values()):.1f}㎍/㎥",
               "체감은 최근 쪽으로 쏠립니다. 두 해 차이는 생각보다 작습니다."),
    ],
    caveat="CAMS 대기질 모델의 추정값입니다. 에어코리아 측정소 실측값과 "
           "다를 수 있습니다.")

# ── 5. 노동시간 ──────────────────────────────────────────────────
wh = [r for r in load_csv("working_hours.csv") if r["working_hours_omm"]]
latest_year = max(int(r["year"]) for r in wh if r["code"] == "KOR")
cur = owid_countries(wh, latest_year, "working_hours_omm")
kor = cur["South Korea"]
rank = sorted(cur.items(), key=lambda kv: -kv[1])
kor_rank = [k for k, _ in rank].index("South Korea") + 1
longer = kor_rank - 1
past = {int(r["year"]): float(r["working_hours_omm"])
        for r in wh if r["code"] == "KOR"}
y30 = latest_year - 30
drop = past[y30] - kor
trio = {c: cur[c] for c in ("South Korea", "Japan", "Germany") if c in cur}
shortest = min(trio, key=trio.get)
name_ko = {"South Korea": "한국", "Japan": "일본", "Germany": "독일"}

topic(
    "working-hours", "⏰", "우리는 얼마나 일하나",
    "나라별 1인당 연간 노동시간",
    "Our World in Data", "https://ourworldindata.org/grapher/annual-working-hours-per-worker",
    [
        slider("w1", f"{latest_year}년 한국의 1인당 연간 노동시간은?",
               kor, "시간", 1200, 2600, 50,
               f"{latest_year}년 한국 {kor:,.0f}시간 "
               f"(주 5일 기준 하루 약 {kor / 250:.1f}시간)",
               "연 단위로 물으면 감이 잘 안 옵니다. 하루로 나눠 보면 체감과 "
               "맞는지 확인할 수 있습니다."),
        slider("w2", f"한국보다 더 오래 일하는 나라는 {len(cur)}개국 중 몇 개일까요?",
               longer, "개국", 0, 60, 1,
               f"{latest_year}년 기준 {len(cur)}개국 중 한국은 {kor_rank}위",
               "'한국이 제일 많이 일한다'는 인상이 강하지만, 비교 대상에 따라 "
               "순위가 달라집니다."),
        slider("w3", f"한국의 노동시간은 30년 전({y30}년)보다 몇 시간 줄었을까요?",
               drop, "시간", 0, 900, 50,
               f"{y30}년 {past[y30]:,.0f}시간 → {latest_year}년 {kor:,.0f}시간",
               "줄어든 폭은 대개 과소평가됩니다. 하루로 치면 크게 달라진 값입니다."),
        choice("w4", "한국·일본·독일 중 가장 적게 일하는 나라는?",
               ["한국", "일본", "독일"], name_ko[shortest],
               " · ".join(f"{name_ko[c]} {trio[c]:,.0f}시간" for c in trio),
               "나라마다 통계 기준이 다릅니다. 순위보다 격차의 크기를 봅니다."),
        slider("w5", "한국과 독일의 연간 노동시간 차이는?",
               abs(cur["South Korea"] - cur["Germany"]), "시간", 0, 900, 50,
               f"한국 {cur['South Korea']:,.0f} · 독일 "
               f"{cur['Germany']:,.0f}시간",
               "두 나라 차이를 주 단위로 나눠 보면 체감이 확 달라집니다."),
    ],
    caveat="이 자료에는 개발도상국이 많이 포함돼 있어, OECD 안에서의 순위와 "
           "전체 순위가 다릅니다. '어느 집단과 비교하느냐'가 순위를 만듭니다.")

# ── 6. 인구와 출산 ───────────────────────────────────────────────
fert = [r for r in load_json("wb_fertility.json")[1] if r["value"] is not None]
f_latest = max(int(r["date"]) for r in fert if r["countryiso3code"] == "KOR")
f_cur = wb_countries(fert, f_latest)
kor_f = f_cur["Korea, Rep."]
f_rank = sorted(f_cur.items(), key=lambda kv: kv[1])
kor_f_rank = [k for k, _ in f_rank].index("Korea, Rep.") + 1
kor_1970 = next(r["value"] for r in fert
                if r["countryiso3code"] == "KOR" and r["date"] == "1970")

pop = load_json("wb_pop_kor.json")[1]
tot = {int(r["date"]): r["value"] for r in pop
       if r["indicator"]["id"] == "SP.POP.TOTL" and r["value"]}
old = {int(r["date"]): r["value"] for r in pop
       if r["indicator"]["id"] == "SP.POP.65UP.TO.ZS" and r["value"]}
urb = {int(r["date"]): r["value"] for r in pop
       if r["indicator"]["id"] == "SP.URB.TOTL.IN.ZS" and r["value"]}
peak_year = max(tot, key=tot.get)
old_latest = max(old)
urb_latest = max(urb)

topic(
    "population", "👶", "인구와 출산",
    "전 세계 출산율과 한국의 인구 구조",
    "World Bank Open Data", "https://data.worldbank.org/",
    [
        slider("p1", f"{f_latest}년 한국의 합계출산율(여성 1명당 출생아 수)은?",
               kor_f, "명", 0.5, 3.0, 0.05,
               f"{f_latest}년 한국 {kor_f:.2f}명",
               "숫자는 자주 들었어도 '여성 1명당'이라는 단위는 잘 안 와닿습니다."),
        slider("p2", f"출산율이 낮은 순으로 세면 한국은 {len(f_cur)}개 나라·지역 중 몇 위일까요?",
               kor_f_rank, "위", 1, 30, 1,
               f"{f_latest}년 기준 {len(f_cur)}곳 중 {kor_f_rank}위 "
               f"(1위 {f_rank[0][0]} {f_rank[0][1]:.2f})",
               "'꼴찌'라고 알고 있지만, 비교 목록에 어떤 나라·지역이 들어가느냐에 "
               "따라 순위가 달라집니다."),
        slider("p3", "1970년 한국의 출산율은 몇 명이었을까요?",
               kor_1970, "명", 1.0, 7.0, 0.1,
               f"1970년 {kor_1970:.2f}명 → {f_latest}년 {kor_f:.2f}명",
               "한 세대 만에 일어난 변화의 크기는 대개 과소평가됩니다."),
        slider("p4", f"{old_latest}년 한국에서 65세 이상 인구의 비율은?",
               old[old_latest], "%", 5, 35, 1,
               f"{old_latest}년 {old[old_latest]:.1f}% "
               f"(World Bank 최신 공표치. 최근 연도는 추계값입니다)",
               "고령화는 '다가올 일'로 느껴지지만 이미 지나온 숫자입니다."),
        slider("p5", f"{urb_latest}년 한국에서 도시에 사는 사람의 비율은?",
               urb[urb_latest], "%", 50, 100, 1,
               f"{urb_latest}년 {urb[urb_latest]:.1f}% "
               f"(World Bank 최신 공표치. 최근 연도는 추계값입니다)",
               "'절반쯤'이라고 답하기 쉽지만 한국은 세계에서도 손꼽히는 도시 국가입니다."),
    ])

# ── 7. 인터넷 ────────────────────────────────────────────────────
net = [r for r in load_json("wb_internet.json")[1] if r["value"] is not None]
n_latest = max(int(r["date"]) for r in net if r["countryiso3code"] == "KOR")
n_cur = wb_countries(net, n_latest)
kor_n = n_cur["Korea, Rep."]
n_rank = sorted(n_cur.items(), key=lambda kv: -kv[1])
kor_n_rank = [k for k, _ in n_rank].index("Korea, Rep.") + 1
kor_2000 = next(r["value"] for r in net
                if r["countryiso3code"] == "KOR" and r["date"] == "2000")
world = next((r["value"] for r in net
              if r["countryiso3code"] == "WLD" and int(r["date"]) == n_latest), None)
if world is None:
    world = mean(n_cur.values())
offline = 100 - world

topic(
    "internet", "🌐", "인터넷과 연결",
    "나라별 인터넷 사용 인구 비율",
    "World Bank Open Data", "https://data.worldbank.org/",
    [
        slider("i1", f"{n_latest}년 한국에서 인터넷을 쓰는 사람의 비율은?",
               kor_n, "%", 60, 100, 1,
               f"{n_latest}년 한국 {kor_n:.1f}%",
               "'거의 다'라고 생각하지만 100%는 아닙니다. 남은 몇 %가 누구인지가 "
               "정책의 대상입니다."),
        slider("i2", f"한국보다 인터넷 사용률이 높은 나라는 {len(n_cur)}곳 중 몇 곳일까요?",
               kor_n_rank - 1, "곳", 0, 60, 1,
               f"{n_latest}년 {len(n_cur)}곳 중 한국 {kor_n_rank}위",
               "'IT 강국'이라는 말과 실제 보급률 순위는 다른 이야기입니다."),
        slider("i3", "2000년 한국의 인터넷 사용률은?",
               kor_2000, "%", 0, 100, 5,
               f"2000년 {kor_2000:.1f}% → {n_latest}년 {kor_n:.1f}%",
               "20여 년 전을 떠올릴 때는 지금의 기준으로 과대평가하기 쉽습니다."),
        slider("i4", f"{n_latest}년 전 세계 평균 인터넷 사용률은?",
               world, "%", 20, 100, 5,
               f"{n_latest}년 세계 {world:.1f}%",
               "내 주변이 전부 연결돼 있으면 세계도 그럴 거라고 생각하게 됩니다."),
        slider("i5", "전 세계에서 인터넷을 쓰지 않는 사람은 몇 %일까요?",
               offline, "%", 0, 70, 5,
               f"100 - {world:.1f} = {offline:.1f}%",
               "같은 사실을 뒤집어 물으면 전혀 다른 크기로 느껴집니다."),
    ])

# ── 8. 환율 ──────────────────────────────────────────────────────
fx = load_json("usdkrw.json")["rates"]
FX = sorted((d, v["KRW"]) for d, v in fx.items() if "KRW" in v)
hi_d, hi_v = max(FX, key=lambda x: x[1])
lo_d, lo_v = min(FX, key=lambda x: x[1])
avg_fx = mean(v for _, v in FX)
under1200 = sum(1 for _, v in FX if v < 1200) / len(FX) * 100
last_d, last_v = FX[-1]
era = ("1997~1999년 외환위기" if hi_d < "2005" else
       "2008~2009년 금융위기" if hi_d < "2012" else
       "2020년 코로나" if hi_d < "2022" else "2022년 이후")

topic(
    "usdkrw", "💵", "원달러 환율 26년",
    "1999년부터 오늘까지의 원달러 환율",
    "Frankfurter (유럽중앙은행 고시)", "https://frankfurter.dev/",
    [
        slider("x1", "1999년 이후 원달러 환율의 최고 기록은?",
               hi_v, "원", 1100, 1800, 25,
               f"{hi_d} {hi_v:,.2f}원",
               "최고치는 위기의 기억과 함께 남지만, 정확한 시점은 자주 헷갈립니다."),
        choice("x2", "그 최고치를 찍은 시기는?",
               ["1997~1999년 외환위기", "2008~2009년 금융위기",
                "2020년 코로나", "2022년 이후"], era,
               f"최고 {hi_v:,.2f}원 ({hi_d}). 이 데이터는 1999년부터라 "
               f"1997~98년 외환위기 구간은 포함되어 있지 않습니다",
               "데이터가 시작하는 시점을 확인하지 않으면 '역대 최고'를 잘못 "
               "말하게 됩니다."),
        slider("x3", "26년간의 평균 환율은?",
               avg_fx, "원", 900, 1500, 25,
               f"{FX[0][0]} ~ {FX[-1][0]} 거래일 {len(FX):,}일 평균 "
               f"{avg_fx:,.0f}원 (최저 {lo_v:,.0f}원 · {lo_d})",
               "최근 값이 기준점이 되어 과거 평균을 높게 잡게 됩니다."),
        slider("x4", "환율이 1,200원 아래였던 날은 전체의 몇 %일까요?",
               under1200, "%", 0, 100, 5,
               f"거래일 {len(FX):,}일 중 1,200원 미만은 "
               f"{sum(1 for _, v in FX if v < 1200):,}일",
               "'원래 1,100원대였는데'라는 감각이 맞는지 비율로 확인해 봅니다."),
        slider("x5", f"{last_d} 기준 환율은?",
               last_v, "원", 1100, 1800, 25,
               f"{last_d} {last_v:,.2f}원",
               "가장 최근 값조차 기억은 며칠 전 뉴스에 묶여 있습니다."),
    ])

# ── 9. 도시 비교 ─────────────────────────────────────────────────
CITY = {}
for cid in ("seoul", "tokyo", "london", "singapore"):
    _d = load_json(f"city_{cid}.json")["daily"]
    CITY[cid] = [{"d": dt.date.fromisoformat(t), "hi": a, "lo": b, "r": c}
                 for t, a, b, c in zip(_d["time"], _d["temperature_2m_max"],
                                       _d["temperature_2m_min"],
                                       _d["precipitation_sum"])]
CN = {"seoul": "서울", "tokyo": "도쿄", "london": "런던", "singapore": "싱가포르"}
YRS = 30
c_rain = {k: sum(x["r"] for x in v) / YRS for k, v in CITY.items()}
c_days = {k: sum(1 for x in v if x["r"] >= 1) / YRS for k, v in CITY.items()}
c_temp = {k: mean((x["hi"] + x["lo"]) / 2 for x in v) for k, v in CITY.items()}
c_hot = {k: max(x["hi"] for x in v) for k, v in CITY.items()}
c_jan = {k: mean(x["lo"] for x in v if x["d"].month == 1) for k, v in CITY.items()}
dry = min(c_rain, key=c_rain.get)
hottest = max(c_hot, key=c_hot.get)
colder = "서울" if c_jan["seoul"] < c_jan["tokyo"] else "도쿄"

topic(
    "cities", "🏙️", "서울·도쿄·런던·싱가포르",
    "네 도시의 30년 평년값 (1991~2020)",
    "Open-Meteo Archive (ERA5 재분석)", "https://open-meteo.com/",
    [
        choice("c1", "1년 강수량이 가장 적은 도시는?",
               ["서울", "도쿄", "런던", "싱가포르"], CN[dry],
               " · ".join(f"{CN[k]} {c_rain[k]:,.0f}mm" for k in CITY),
               "비가 자주 오는 것과 많이 오는 것은 다릅니다. 런던은 자주 오지만 "
               "적게 옵니다."),
        slider("c2", "런던에서 1년에 비가 오는 날(1mm 이상)은 며칠일까요?",
               c_days["london"], "일", 40, 220, 5,
               f"런던 {c_days['london']:.0f}일 · 서울 {c_days['seoul']:.0f}일 "
               f"(강수량은 런던 {c_rain['london']:,.0f}mm · "
               f"서울 {c_rain['seoul']:,.0f}mm)",
               "런던은 서울보다 비 오는 날이 많은데 총량은 절반입니다. "
               "'며칠 왔나'와 '얼마나 왔나'는 다른 질문입니다."),
        choice("c3", "30년간 가장 높은 기온을 기록한 도시는?",
               ["서울", "도쿄", "런던", "싱가포르"], CN[hottest],
               " · ".join(f"{CN[k]} {c_hot[k]:.1f}도" for k in CITY),
               "적도에 가까울수록 덥다고 생각하지만, 최고기온 기록은 중위도 "
               "도시에서 나옵니다."),
        slider("c4", "서울의 연평균 기온은?",
               c_temp["seoul"], "도", 5, 30, 0.5,
               " · ".join(f"{CN[k]} {c_temp[k]:.1f}도" for k in CITY),
               "여름과 겨울의 기억이 강해서 연평균은 감이 잘 안 옵니다."),
        choice("c5", "1월 밤이 더 추운 도시는?",
               ["서울", "도쿄"], colder,
               f"1월 평균 최저기온 서울 {c_jan['seoul']:.1f}도 · "
               f"도쿄 {c_jan['tokyo']:.1f}도",
               "위도가 비슷해도 대륙의 영향을 받는 도시가 훨씬 춥습니다."),
    ],
    caveat="ERA5 재분석 값이고, 도시별로 관측소 위치와 기준이 다릅니다.")

# ── 10. 지진 ─────────────────────────────────────────────────────
Q = [f["properties"] for f in load_json("quakes.geojson")["features"]]
QK = [f["properties"] for f in load_json("quakes_korea.geojson")["features"]]
n_years = 25
per_year = len(Q) / n_years
m7 = sum(1 for p in Q if p["mag"] >= 7.0) / n_years
biggest = max(Q, key=lambda p: p["mag"])


def region(place):
    return (place or "").split(",")[-1].strip()


top_region = Counter(region(p["place"]) for p in Q).most_common(1)[0]
region_ko = {"Japan": "일본", "Indonesia": "인도네시아", "Chile": "칠레",
             "Philippines": "필리핀"}
kr_band = ("50건 미만" if len(QK) < 50 else "50~150건" if len(QK) <= 150
           else "150~400건" if len(QK) <= 400 else "400건 이상")

topic(
    "quakes", "🌎", "지진은 얼마나 자주",
    "2000~2024년 전 세계 지진 기록",
    "USGS 지진 카탈로그", "https://earthquake.usgs.gov/",
    [
        slider("q1", "규모 5.5 이상 지진은 전 세계에서 1년에 몇 번쯤 일어날까요?",
               per_year, "회", 50, 1200, 50,
               f"2000~2024년 {len(Q):,}건 ÷ {n_years}년 = "
               f"연평균 {per_year:.0f}회",
               "뉴스에 나오는 지진만 세면 실제보다 훨씬 적게 잡게 됩니다."),
        slider("q2", "규모 7.0 이상은 1년에 몇 번쯤일까요?",
               m7, "회", 0, 40, 1,
               f"2000~2024년 규모 7.0 이상 "
               f"{sum(1 for p in Q if p['mag'] >= 7.0)}건, 연평균 {m7:.1f}회",
               "규모는 로그 척도입니다. 0.5만 올라가도 횟수가 크게 줄어듭니다."),
        choice("q3", "규모 5.5 이상 지진이 가장 자주 기록된 나라는?",
               ["일본", "인도네시아", "칠레", "필리핀"],
               region_ko.get(top_region[0], "인도네시아"),
               f"1위 {top_region[0]} {top_region[1]:,}건",
               "지진 하면 떠오르는 나라와 실제로 가장 많이 기록되는 곳은 "
               "다를 수 있습니다."),
        slider("q4", "2000년 이후 기록된 가장 큰 지진의 규모는?",
               biggest["mag"], "", 7.0, 9.9, 0.1,
               f"규모 {biggest['mag']} · "
               f"{dt.datetime.fromtimestamp(biggest['time'] / 1000, dt.UTC):%Y-%m-%d} "
               f"{biggest['place']}",
               "규모 9는 8보다 약 32배 큰 에너지입니다."),
        choice("q5", "한반도 주변(위도 33~39.5도)에서 25년간 기록된 규모 3.0 이상 지진은?",
               ["50건 미만", "50~150건", "150~400건", "400건 이상"], kr_band,
               f"USGS 기준 {len(QK)}건. 이 관측망은 작은 지진을 모두 잡지는 "
               f"못하므로 기상청 집계와 다릅니다",
               "'어느 기관이 센 숫자인가'를 확인하지 않으면 같은 현상도 다른 "
               "값이 됩니다."),
    ],
    caveat="USGS 카탈로그는 작은 지진을 모두 담지 못합니다. 한반도 지진은 "
           "기상청 집계가 더 많습니다.")

# ── 11. 수명 ─────────────────────────────────────────────────────
le = [r for r in load_csv("life_expectancy.csv") if r["life_expectancy_0"]]
l_latest = max(int(r["year"]) for r in le if r["code"] == "KOR")
l_cur = owid_countries(le, l_latest, "life_expectancy_0")
kor_l = l_cur["South Korea"]
l_rank = sorted(l_cur.items(), key=lambda kv: -kv[1])
kor_l_rank = [k for k, _ in l_rank].index("South Korea") + 1
_kle = {r["year"]: float(r["life_expectancy_0"]) for r in le if r["code"] == "KOR"}
kor_1950, kor_1953, kor_1955 = _kle["1950"], _kle["1953"], _kle["1955"]
wld = next(float(r["life_expectancy_0"]) for r in le
           if r["code"] == "OWID_WRL" and int(r["year"]) == l_latest)
trio_l = {c: l_cur[c] for c in ("South Korea", "Japan", "United States")
          if c in l_cur}
top_l = max(trio_l, key=trio_l.get)
name_l = {"South Korea": "한국", "Japan": "일본", "United States": "미국"}

topic(
    "life", "🩺", "얼마나 오래 사나",
    "나라별 기대수명 1950~현재",
    "Our World in Data", "https://ourworldindata.org/grapher/life-expectancy",
    [
        slider("l1", f"{l_latest}년 한국의 기대수명은?",
               kor_l, "세", 60, 95, 1,
               f"{l_latest}년 한국 {kor_l:.1f}세",
               "기대수명은 '지금 태어난 아이가 평균적으로 살 햇수'입니다. "
               "지금 살아 있는 사람의 예상 수명과는 다릅니다."),
        slider("l2", f"기대수명이 긴 순으로 세면 한국은 {len(l_cur)}곳 중 몇 위일까요?",
               kor_l_rank, "위", 1, 60, 1,
               f"{l_latest}년 {len(l_cur)}곳 중 {kor_l_rank}위 "
               f"(1위 {l_rank[0][0]} {l_rank[0][1]:.1f}세)",
               "상위권인 것은 맞지만 몇 위인지는 대개 크게 빗나갑니다."),
        slider("l3", "1950년 한국의 기대수명은?",
               kor_1950, "세", 20, 70, 1,
               f"1950년 {kor_1950:.1f}세. 한국전쟁 기간의 사망이 반영된 값이라 "
               f"1953년 {kor_1953:.1f}세, 1955년 {kor_1955:.1f}세로 빠르게 "
               f"회복합니다. {l_latest}년은 {kor_l:.1f}세",
               "숫자가 튀면 사건을 의심해야 합니다. 이 값은 오류가 아니라 "
               "전쟁의 기록입니다."),
        choice("l4", "한국·일본·미국 중 기대수명이 가장 긴 나라는?",
               ["한국", "일본", "미국"], name_l[top_l],
               " · ".join(f"{name_l[c]} {trio_l[c]:.1f}세" for c in trio_l),
               "가장 잘사는 나라가 가장 오래 사는 나라는 아닙니다."),
        slider("l5", f"{l_latest}년 세계 평균 기대수명은?",
               wld, "세", 50, 90, 1,
               f"{l_latest}년 세계 평균 {wld:.1f}세 · 한국 {kor_l:.1f}세",
               "내가 사는 곳의 수준을 세계 평균으로 착각하기 쉽습니다."),
    ])

# ── 12. DRAM 가격 ────────────────────────────────────────────────
# 계산은 위쪽 dram() 에 있다 (--only dram 으로 이 주제만 다시 쓸 수 있게)
dram()

# ── 13. 엔화 ─────────────────────────────────────────────────────
jpykrw()

# ── 14. 서울 아파트 ──────────────────────────────────────────────
seoul_apt()


# ════════════════════════════════════════════════════════════════
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for t in TOPICS:
        assert len(t["questions"]) == 5, f"{t['id']}: 문항이 5개가 아닙니다"
        index.append(write_pack(t))

    # 제목·부제는 화면을 바꾸며 고친 값을 지킨다 (2장에서 내 제목으로 바꾼다).
    # 다시 계산해도 내 제목이 «감 테스트»로 돌아가지 않게, 있던 값을 읽어 쓴다
    old = {}
    if (APP / "topics.json").exists():
        try:
            old = json.load(io.open(APP / "topics.json", encoding="utf-8"))
        except ValueError:
            old = {}
    io.open(APP / "topics.json", "w", encoding="utf-8").write(json.dumps({
        "title": old.get("title", "더 이상 감에 의존할 수 없다!"),
        "subtitle": old.get("subtitle", "당신은 부채 도사가 아닙니다. 전문가로 만들어 드립니다."),
        # 등급·문구는 여기서 고칩니다. 코드를 건드릴 일이 아닙니다
        "grades": [
            {"min": 90, "name": "촉이 데이터급", "emoji": "🎯"},
            {"min": 70, "name": "감이 좋은 편", "emoji": "📊"},
            {"min": 50, "name": "보통의 감각", "emoji": "🙂"},
            {"min": 30, "name": "느낌대로 삽니다", "emoji": "🎲"},
            {"min": 0, "name": "감은 접어두시죠", "emoji": "🙈"},
        ],
        "reactions_choice": {"hit": "맞히셨습니다", "miss": "다들 그렇게 찍습니다"},
        "reactions": [
            {"max": 5, "text": "촉이 좋으시네요"},
            {"max": 20, "text": "비슷하게 보셨습니다"},
            {"max": 60, "text": "음…"},
            {"max": 999, "text": "꽤 멀리 가셨습니다"},
        ],
        "topics": index,
    }, ensure_ascii=False, indent=2))

    # 사람이 읽는 정답지
    md = [f"# 문항 정답지 — {len(TOPICS)}주제 {sum(len(t['questions']) for t in TOPICS)}문항", "",
          "> 모든 값은 `data/raw/` 의 원본에서 `tools/build_topics.py` 가 계산합니다.", ""]
    for t in TOPICS:
        md += [f"## {t['emoji']} {t['title']}", "",
               f"- 출처: {t['source']} · {t['source_url']}"]
        if t["caveat"]:
            md += [f"- **한계** {t['caveat']}"]
        md += [""]
        for q in t["questions"]:
            a = f"{q['answer']}{q.get('unit', '')}" if q["type"] == "slider" \
                else q["answer"]
            md += [f"**{q['text']}**", "",
                   f"- 정답 **{a}**", f"- 근거 {q['basis']}",
                   f"- 왜 틀리나 {q['why']}", ""]
    io.open(HERE / "정답지.md", "w", encoding="utf-8").write("\n".join(md))

    print(f"주제 {len(TOPICS)}개 · 문항 {sum(len(t['questions']) for t in TOPICS)}개")
    for t in TOPICS:
        print(f"\n{t['emoji']} {t['title']}  ({t['source']})")
        for q in t["questions"]:
            a = f"{q['answer']}{q.get('unit', '')}" if q["type"] == "slider" \
                else q["answer"]
            print(f"    [{q['type'][:6]:<6}] {q['text'][:44]:<44} → {a}")


if __name__ == "__main__":
    main()
