"""
329200 (TIGER 리츠부동산인프라) 매수 감시 & 텔레그램 알림 스크립트

매일 GitHub Actions로 실행되어:
  1. 네이버 금융 공개 API로 실시간 주가를 가져오고
  2. FRED API로 미국 10년물 국채금리를 가져오고
  3. 간단한 점수 로직으로 매수 판정을 계산한 뒤
  4. 텔레그램으로 리포트를 발송합니다.

API 키/토큰은 절대 코드에 하드코딩하지 않고 환경변수(GitHub Secrets)로 주입받습니다.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import requests

# ── 환경변수 (GitHub Actions Secrets에서 주입) ──────────────────────────
FRED_API_KEY = os.environ.get("FRED_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STOCK_CODE = "329200"  # TIGER 리츠부동산인프라

# 매수 판정 기준값 (필요에 따라 조정하세요)
PRICE_THRESHOLD = 4000       # 이 가격 이하이면 가점
RATE_THRESHOLD = 4.5         # 미 10년물 금리가 이 이하이면 가점


def get_stock_price(code: str) -> dict:
    """네이버 금융 공개 API에서 실시간 시세를 가져옵니다."""
    url = f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    data = res.json()
    item = data["datas"][0]
    return {
        "price": int(item["closePrice"].replace(",", "")),
        "change": item.get("compareToPreviousClosePrice"),
        "change_rate": item.get("fluctuationsRatio"),
        "market_status": item.get("marketStatus"),
    }


def get_us10y_yield(api_key: str) -> float:
    """FRED API에서 미국 10년물 국채금리(DGS10) 최신값을 가져옵니다."""
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=DGS10&api_key={api_key}&file_type=json"
        "&sort_order=desc&limit=5"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    observations = res.json()["observations"]
    # 휴장일 등으로 값이 "."(결측)인 경우를 건너뛰고 최신 유효값을 찾음
    for obs in observations:
        if obs["value"] != ".":
            return float(obs["value"])
    raise ValueError("최근 관측치에서 유효한 금리 값을 찾지 못했습니다.")


def calc_score(price: int, us10y: float) -> tuple[int, str]:
    score = 0
    if price <= PRICE_THRESHOLD:
        score += 3
    if us10y <= RATE_THRESHOLD:
        score += 3

    if score >= 6:
        status = "🟢 [1차 분할매수 우호]"
    elif score >= 3:
        status = "🟡 [관심구간 / 관망]"
    else:
        status = "🔴 [매수 비우호]"
    return score, status


def build_message(price_info: dict, us10y: float, score: int, status: str) -> str:
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst).strftime("%Y-%m-%d %H:%M")
    return (
        f"[329200 매수 감시 시스템 - Daily Report]\n"
        f"🕒 {now} (KST)\n\n"
        f"1. 시장 지표 현황\n"
        f"• TIGER 리츠부동산인프라: {price_info['price']:,}원 "
        f"({price_info.get('change_rate', 'N/A')}%)\n"
        f"• 미국 10년물 국채금리: {us10y:.2f}%\n\n"
        f"2. 종합 매수 판정\n"
        f"• 매수 평가 점수: {score} / 6점\n"
        f"• 최종 판정: {status}\n\n"
        f"※ 본 알림은 참고용 지표이며 투자 판단과 책임은 본인에게 있습니다."
    )


def send_telegram(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    res = requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=10)
    res.raise_for_status()


def main() -> None:
    missing = [
        name
        for name, val in [
            ("FRED_API_KEY", FRED_API_KEY),
            ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
            ("TELEGRAM_CHAT_ID", CHAT_ID),
        ]
        if not val
    ]
    if missing:
        print(f"필수 환경변수가 없습니다: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    price_info = get_stock_price(STOCK_CODE)
    us10y = get_us10y_yield(FRED_API_KEY)
    score, status = calc_score(price_info["price"], us10y)
    message = build_message(price_info, us10y, score, status)

    print(message)  # GitHub Actions 로그에도 남김
    send_telegram(TELEGRAM_TOKEN, CHAT_ID, message)


if __name__ == "__main__":
    main()
