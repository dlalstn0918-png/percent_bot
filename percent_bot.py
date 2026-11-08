#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Percent Bot - 네이버 쇼핑 실시간 최저가 탐색 봇
대상 상품: 농심 신라면 봉지 20개입
카카오톡 '나에게 보내기' 알림 기능 포함
"""

import os
import sys
import json
import re
import urllib.request
import urllib.parse

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

TARGET_KEYWORD = "농심 신라면 봉지 20개입"
SUPPLEMENT_KEYWORDS = ["농심 신라면 120g 20개", "신라면 20개"]
TARGET_PRICE = 15000

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ==============================================================================
# 카카오톡 인증 및 '나에게 보내기' 알림 함수
# ==============================================================================

def load_env():
    """프로젝트 루트의 .env (또는 .env.txt) 파일에서 환경 변수를 읽어 딕셔너리로 반환"""
    env_vars = {}
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(base_dir, ".env"), os.path.join(base_dir, ".env.txt")]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            env_vars[k.strip()] = v.strip()
            except Exception:
                pass
    return env_vars

def update_env_refresh_token(new_refresh_token):
    """새로운 리프레시 토큰이 발급되었을 때 .env 파일에 업데이트"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(base_dir, ".env"), os.path.join(base_dir, ".env.txt")]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.rstrip("\r\n") for line in f]
                updated_lines = [l for l in lines if not l.startswith("KAKAO_REFRESH_TOKEN=")]
                updated_lines.append(f"KAKAO_REFRESH_TOKEN={new_refresh_token}")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(updated_lines) + "\n")
            except Exception:
                pass

def get_kakao_access_token(env_vars):
    """
    .env 파일의 정보를 바탕으로 카카오 Access Token을 발급받거나 갱신합니다.
    """
    client_id = env_vars.get("KAKAO_REST_API_KEY")
    client_secret = env_vars.get("KAKAO_CLIENT_SECRET")
    refresh_token = env_vars.get("KAKAO_REFRESH_TOKEN")
    access_token = env_vars.get("KAKAO_ACCESS_TOKEN")

    if not client_id:
        raise ValueError(".env에 'KAKAO_REST_API_KEY' 항목이 없습니다.")

    # 1. 리프레시 토큰이 있는 경우 최신 액세스 토큰으로 갱신
    if refresh_token:
        url = "https://kauth.kakao.com/oauth/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }
        if client_secret:
            data["client_secret"] = client_secret

        encoded = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                new_access_token = resp_json.get("access_token")
                # 리프레시 토큰 유효기간이 1개월 미만이면 새 리프레시 토큰도 함께 옴
                new_refresh_token = resp_json.get("refresh_token")
                if new_refresh_token:
                    update_env_refresh_token(new_refresh_token)
                if new_access_token:
                    return new_access_token
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"카카오 토큰 갱신 실패 (HTTP {e.code}): {err_body}")
        except Exception as e:
            raise RuntimeError(f"카카오 토큰 갱신 네트워크 오류: {e}")

    # 2. 리프레시 토큰이 없고 access_token만 있는 경우
    if access_token:
        return access_token

    raise ValueError(".env에 'KAKAO_REFRESH_TOKEN'이 설정되어 있지 않습니다.")

def send_kakao_talk_memo(item):
    """
    1위 상품 정보를 카카오톡 '나에게 보내기'로 전송합니다.
    상품명, 가격, 쇼핑몰 이름, 리뷰 수를 넣고 '구매하러 가기' 버튼을 포함합니다.
    알림을 전송하지 못했을 경우 실패 원인을 있는 그대로 출력합니다.
    """
    env_vars = load_env()

    # 1. 인증 토큰 획득
    try:
        access_token = get_kakao_access_token(env_vars)
    except Exception as e:
        print(f"❌ [카카오톡 알림 실패] 인증 토큰을 가져오지 못했습니다: {e}\n")
        return False

    # 2. 메시지 본문 구성 (상품명, 가격, 쇼핑몰, 리뷰수)
    deliv_text = f"{item['delivery_fee']:,}원" if item.get('delivery_fee', 0) > 0 else "무료배송"
    total_text = f"{item.get('total', item['price']):,}원"
    review_text = f"{item.get('review_count', 0):,}건"
    mall_name = item.get("mall_name", "쇼핑몰")
    url = item.get("url") or "https://shopping.naver.com"

    text_content = (
        f"🚨 [특가 발생] 신라면 20개 최저가 알림!\n\n"
        f"• 상품명: {item['title']}\n"
        f"• 가  격: {item['price']:,}원 (배송비: {deliv_text} / 합계: {total_text})\n"
        f"• 쇼핑몰: {mall_name}\n"
        f"• 리뷰수: {review_text}"
    )

    template_object = {
        "object_type": "text",
        "text": text_content,
        "link": {
            "web_url": url,
            "mobile_web_url": url,
        },
        "button_title": "구매하러 가기",
    }

    send_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    post_data = urllib.parse.urlencode({
        "template_object": json.dumps(template_object, ensure_ascii=False)
    }).encode("utf-8")

    req = urllib.request.Request(
        send_url,
        data=post_data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            res_json = json.loads(resp_body)
            if res_json.get("result_code") == 0:
                print("💬 [카카오톡 알림 전송] 나에게 보내기 메시지를 성공적으로 전송했습니다!\n")
                return True
            else:
                print(f"❌ [카카오톡 알림 실패] 응답 코드 오류: {resp_body}\n")
                return False
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"❌ [카카오톡 알림 실패] 메시지 전송 실패 (HTTP {e.code}): {err_body}\n")
        return False
    except Exception as e:
        print(f"❌ [카카오톡 알림 실패] 네트워크 오류: {e}\n")
        return False

# ==============================================================================
# 네이버 쇼핑 수집 및 상품 필터링
# ==============================================================================

def fetch_naver_shopping(query: str):
    encoded = urllib.parse.quote(query)
    url = f"https://search.naver.com/search.naver?where=nexearch&query={encoded}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"네이버 쇼핑 검색 페이지 연결 실패: {e}")

    start_token = 'naver.search.ext.newshopping["shopping"]._INITIAL_STATE='
    idx = html.find(start_token)
    if idx < 0:
        raise RuntimeError("네이버 쇼핑 응답에서 상품 데이터(_INITIAL_STATE)를 찾을 수 없습니다. (차단되었거나 페이지 구조가 변경되었을 수 있습니다)")

    sub = html[idx + len(start_token):]
    depth = 0
    end_pos = -1
    for i, char in enumerate(sub):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end_pos = i + 1
                break

    if end_pos <= 0:
        raise RuntimeError("네이버 쇼핑 JSON 데이터의 끝 위치를 파악하지 못했습니다.")

    try:
        payload = json.loads(sub[:end_pos])
    except Exception as e:
        raise RuntimeError(f"네이버 쇼핑 JSON 데이터 디코딩 실패: {e}")

    items = []
    paged_slot = payload.get("initProps", {}).get("pagedSlot", [])
    for page in paged_slot:
        for slot in page.get("slots", []):
            d = slot.get("data")
            if not d:
                continue

            raw_title = d.get("productName") or d.get("productNameOrg") or ""
            clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()

            price = d.get("discountedSalePrice") or d.get("salePrice")
            if not clean_title or not price:
                continue

            try:
                price = int(price)
            except (ValueError, TypeError):
                continue

            deliv_info = d.get("productDeliveryInfo", {}) or {}
            deliv_fee = deliv_info.get("deliveryFee") or 0
            try:
                deliv_fee = int(deliv_fee)
            except (ValueError, TypeError):
                deliv_fee = 0

            card_type = d.get("cardType", "")
            source_type = d.get("sourceType", "")
            is_ad = (card_type == "AD_CARD") or (source_type == "AD")

            mall_name = d.get("mallName")
            if not mall_name:
                if card_type == "CATALOG_CARD":
                    mall_count = d.get("shoppingExtraInfo", {}).get("mallCount")
                    mall_name = f"네이버 가격비교 (몰 {mall_count}개)" if mall_count else "네이버 가격비교"
                else:
                    mall_name = "일반몰"

            product_url = d.get("productUrl", {}) or {}
            click_url = d.get("productClickUrl", {}) or {}
            nv_mid = d.get("nvMid")
            if card_type == "CATALOG_CARD" and nv_mid:
                link = f"https://search.shopping.naver.com/catalog/{nv_mid}"
            elif product_url.get("pcUrl"):
                link = product_url.get("pcUrl")
            elif click_url.get("pcUrl"):
                link = click_url.get("pcUrl")
            else:
                link = ""

            items.append({
                "title": clean_title,
                "price": price,
                "delivery_fee": deliv_fee,
                "total": price + deliv_fee,
                "mall_name": mall_name,
                "review_count": int(d.get("totalReviewCount") or 0),
                "is_ad": is_ad,
                "url": link,
            })

    return items

def is_genuine_shin_ramyun_20(item):
    if item["is_ad"]:
        return False

    title = item["title"]

    if "신라면" not in title:
        return False

    # 다른 신라면 라인업 제외
    if re.search(r"건면|블랙|골드|더레드|툼바|볶음면|두부김치|제페토", title):
        return False

    # 다른 라면 혼합 세트 제외
    if re.search(r"안성탕면|짜파게티|너구리|오징어짬뽕|비빔면|골라담기|혼합|세트|4종|3종|\+|교차", title):
        return False

    # 수량 20개 확인
    if not (re.search(r"20개|20봉|20p|20P|20입", title) or re.search(r"120g.*1박스", title)):
        return False

    return True

# ==============================================================================
# 메인 실행 흐름
# ==============================================================================

def main():
    print("=" * 72)
    print("  🍜 농심 신라면 봉지 20개입 최저가 탐색 봇 (percent_bot)")
    print("=" * 72)
    print(f"[1/3] 네이버 쇼핑 실시간 검색 요청 중... ('{TARGET_KEYWORD}')")

    collected = []
    try:
        collected.extend(fetch_naver_shopping(TARGET_KEYWORD))
    except Exception as e:
        print(f"\n❌ [오류 발생] {e}")
        print("프로그램을 중단합니다.")
        sys.exit(1)

    genuine = [it for it in collected if is_genuine_shin_ramyun_20(it)]

    if len(genuine) < 3:
        print(f"[정보] '{TARGET_KEYWORD}' 검색 결과 중 순수 신라면 20개 비광고 상품이 부족하여 추가 검색을 진행합니다...")
        for supp_q in SUPPLEMENT_KEYWORDS:
            try:
                supp_items = fetch_naver_shopping(supp_q)
                collected.extend(supp_items)
                genuine = [it for it in collected if is_genuine_shin_ramyun_20(it)]
                if len(genuine) >= 5:
                    break
            except Exception:
                pass

    # URL 기준 중복 제거
    seen_urls = set()
    dedup = []
    for it in genuine:
        if it["url"] and it["url"] not in seen_urls:
            seen_urls.add(it["url"])
            dedup.append(it)

    if not dedup:
        print("\n❌ [결과 없음] 검색 결과에서 광고가 아니며 조건에 부합하는 '신라면 20개' 상품을 찾지 못했습니다.")
        print("조회 시점 기준 네이버 쇼핑 노출 상품이 없거나 필터 조건에 매칭되지 않았습니다.")
        sys.exit(1)

    # 가격 오름차순 정렬
    sorted_items = sorted(dedup, key=lambda x: x["price"])
    top3 = sorted_items[:3]

    print(f"[2/3] 광고 상품 제거 및 순수 신라면 20개 필터링 완료 (총 {len(sorted_items)}개 중 상위 {len(top3)}개)\n")

    for rank, item in enumerate(top3, start=1):
        deliv_text = f"{item['delivery_fee']:,}원" if item['delivery_fee'] > 0 else "무료배송"
        print("-" * 72)
        print(f"  🏅 {rank}위: {item['title']}")
        print(f"     - 가  격 : {item['price']:,}원 (배송비: {deliv_text} / 합계: {item['total']:,}원)")
        print(f"     - 쇼핑몰 : {item['mall_name']}")
        print(f"     - 리뷰수 : {item['review_count']:,}건")
        print(f"     - 링크 : {item['url']}")
    print("-" * 72)

    print(f"\n[3/3] 목표 가격 판정 (목표가: 15,000원)")
    first_price = top3[0]["price"]
    print(f"      현재 1위 최저가: {first_price:,}원\n")

    if first_price <= TARGET_PRICE:
        print("🚨 [특가 발생] 목표 가격 이하입니다!\n")
        # 1. 1위 가격이 목표가 이하일 때만 카카오톡으로 알림 전송
        send_kakao_talk_memo(top3[0])
    else:
        # 목표가보다 비싸면 화면에만 출력하고 메시지는 보내지 않음
        print("ℹ️ [유지] 아직 목표 가격보다 비쌉니다.\n")

if __name__ == "__main__":
    main()
