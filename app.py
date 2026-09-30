from flask import Flask, jsonify, request
import requests
import re
import html
from urllib.parse import unquote


app = Flask(__name__)

# 한글 JSON을 \uXXXX 형태가 아니라 그대로 표시
app.json.ensure_ascii = False


# ============================================================
# AION2 기본 설정
# ============================================================

BASE_URL = "https://aion2.plaync.com"

DEFAULT_NAME = "갹"
DEFAULT_SERVER_ID = 2012
DEFAULT_RACE = 2


USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/154.0.0.0 "
    "Safari/537.36"
)


# ============================================================
# 공통 헤더
# ============================================================

def make_headers(referer=None):

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    if referer:
        headers["Referer"] = referer

    return headers


# ============================================================
# 검색 결과 캐릭터명 HTML 제거
# ============================================================

def clean_name(value):

    value = re.sub(
        r"<[^>]+>",
        "",
        str(value or "")
    )

    return html.unescape(value).strip()


# ============================================================
# 아이템레벨 추출
# ============================================================

def find_item_level(info):

    if not isinstance(info, dict):
        return None

    stat = info.get("stat") or {}

    stat_list = stat.get("statList") or []

    for item in stat_list:

        if not isinstance(item, dict):
            continue

        if item.get("type") == "ItemLevel":
            return item.get("value")

    return None


# ============================================================
# AION2 캐릭터 검색
# ============================================================

def search_character(
    session,
    name,
    server_id,
    race
):

    search_url = (
        BASE_URL
        + "/ko-kr/api/search/aion2/search/v2/character"
    )

    response = session.get(
        search_url,
        params={
            "keyword": name,
            "race": race,
            "serverId": server_id,
        },
        headers=make_headers(
            BASE_URL + "/ko-kr/"
        ),
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    exact = None

    for item in data.get("list", []):

        item_name = clean_name(
            item.get("name")
        )

        if item_name == name:

            exact = item

            break

    return response, exact


# ============================================================
# AION2 캐릭터 상세 조회
# ============================================================

def get_character_data(
    name,
    server_id,
    race
):

    result = {
        "name": name,
        "serverId": server_id,
        "race": race,
    }


    session = requests.Session()


    # ========================================================
    # 1. 캐릭터 검색
    # ========================================================

    try:

        search_response, exact = search_character(
            session,
            name,
            server_id,
            race
        )

        result["searchHttp"] = (
            search_response.status_code
        )

        result["searchLength"] = len(
            search_response.content
        )

    except Exception as e:

        result["success"] = False

        result["stage"] = "search"

        result["error"] = str(e)

        return result


    if not exact:

        result["success"] = False

        result["stage"] = "search"

        result["error"] = (
            "정확히 일치하는 캐릭터를 찾지 못했습니다."
        )

        return result


    raw_character_id = str(
        exact.get("characterId") or ""
    )


    character_id = unquote(
        raw_character_id
    )


    result["searchResult"] = {
        "name": clean_name(
            exact.get("name")
        ),
        "serverId": exact.get(
            "serverId"
        ),
        "serverName": exact.get(
            "serverName"
        ),
        "level": exact.get(
            "level"
        ),
        "pcId": exact.get(
            "pcId"
        ),
        "characterId": character_id,
        "profileImageUrl": exact.get(
            "profileImageUrl"
        ),
    }


    # ========================================================
    # 2. 캐릭터 정보실 페이지
    # ========================================================

    page_url = (
        BASE_URL
        + "/ko-kr/characters/"
        + str(server_id)
        + "/"
        + raw_character_id
    )


    result["pageUrl"] = page_url


    try:

        page_response = session.get(
            page_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml,"
                    "application/xml;q=0.9,"
                    "*/*;q=0.8"
                ),
                "Accept-Language":
                    "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            timeout=15,
        )


        result["pageHttp"] = (
            page_response.status_code
        )


        result["pageLength"] = len(
            page_response.content
        )


        page_text = page_response.text


        geo_match = re.search(
            r'_geolocationCountry\s*=\s*["\']([^"\']+)["\']',
            page_text,
            re.I,
        )


        country_match = re.search(
            r'data-country\s*=\s*["\']([^"\']+)["\']',
            page_text,
            re.I,
        )


        result["geolocationCountry"] = (
            geo_match.group(1)
            if geo_match
            else None
        )


        result["dataCountry"] = (
            country_match.group(1)
            if country_match
            else None
        )


    except Exception as e:

        result["pageError"] = str(e)


    # ========================================================
    # 공통 상세 API 파라미터
    # ========================================================

    params = {
        "lang": "ko",
        "characterId": character_id,
        "serverId": server_id,
    }


    api_headers = make_headers(
        page_url
    )


    # ========================================================
    # 3. CHARACTER INFO
    # ========================================================

    info = None


    try:

        info_response = session.get(
            BASE_URL
            + "/api/character/info",
            params=params,
            headers=api_headers,
            timeout=15,
        )


        result["infoHttp"] = (
            info_response.status_code
        )


        result["infoLength"] = len(
            info_response.content
        )


        try:

            info = info_response.json()

        except Exception:

            info = None


        result["infoEmpty"] = (
            not isinstance(info, dict)
            or len(info) == 0
        )


        if (
            not isinstance(info, dict)
            or not info
        ):

            result["infoBody"] = (
                info_response.text[:300]
            )


    except Exception as e:

        result["infoError"] = str(e)


    # ========================================================
    # 4. EQUIPMENT
    # ========================================================

    equipment = None


    try:

        equipment_response = session.get(
            BASE_URL
            + "/api/character/equipment",
            params=params,
            headers=api_headers,
            timeout=15,
        )


        result["equipmentHttp"] = (
            equipment_response.status_code
        )


        result["equipmentLength"] = len(
            equipment_response.content
        )


        try:

            equipment = (
                equipment_response.json()
            )

        except Exception:

            equipment = None


        result["equipmentEmpty"] = (
            not isinstance(
                equipment,
                dict
            )
            or len(equipment) == 0
        )


        if (
            not isinstance(
                equipment,
                dict
            )
            or not equipment
        ):

            result["equipmentBody"] = (
                equipment_response.text[:300]
            )


    except Exception as e:

        result["equipmentError"] = str(e)


    # ========================================================
    # 5. GAMEINFO CLASSES
    # ========================================================

    classes = None


    try:

        classes_response = session.get(
            BASE_URL
            + "/api/gameinfo/classes",
            params={
                "lang": "ko"
            },
            headers=make_headers(
                BASE_URL + "/ko-kr/"
            ),
            timeout=15,
        )


        result["classesHttp"] = (
            classes_response.status_code
        )


        result["classesLength"] = len(
            classes_response.content
        )


        try:

            classes = (
                classes_response.json()
            )

        except Exception:

            classes = None


        result["classesEmpty"] = (
            not isinstance(
                classes,
                dict
            )
            or len(classes) == 0
        )


    except Exception as e:

        result["classesError"] = str(e)


    # ========================================================
    # 정상 데이터 추출
    # ========================================================

    if (
        isinstance(info, dict)
        and info
    ):

        profile = (
            info.get("profile")
            or {}
        )


        result["character"] = {

            "name":
                profile.get(
                    "characterName"
                ),

            "className":
                profile.get(
                    "className"
                ),

            "combatPower":
                profile.get(
                    "combatPower"
                ),

            "itemLevel":
                find_item_level(
                    info
                ),

            "level":
                profile.get(
                    "characterLevel"
                ),

            "pcId":
                profile.get(
                    "pcId"
                ),

            "raceName":
                profile.get(
                    "raceName"
                ),

            "serverId":
                profile.get(
                    "serverId"
                ),

            "serverName":
                profile.get(
                    "serverName"
                ),

            "regionName":
                profile.get(
                    "regionName"
                ),

            "profileImage":
                profile.get(
                    "profileImage"
                ),
        }


    # ========================================================
    # 장비 개수
    # ========================================================

    if (
        isinstance(equipment, dict)
        and equipment
    ):

        equipment_data = (
            equipment.get("equipment")
            or {}
        )


        equipment_list = (
            equipment_data.get(
                "equipmentList"
            )
            or []
        )


        result["equipmentCount"] = len(
            equipment_list
        )


    # ========================================================
    # 최종 성공 여부
    # ========================================================

    info_ok = (
        result.get("infoHttp") == 200
        and result.get("infoEmpty") is False
    )


    equipment_ok = (
        result.get("equipmentHttp") == 200
        and result.get(
            "equipmentEmpty"
        ) is False
    )


    classes_ok = (
        result.get("classesHttp") == 200
        and result.get(
            "classesEmpty"
        ) is False
    )


    result["success"] = (
        info_ok
        and equipment_ok
        and classes_ok
    )


    if result["success"]:

        result["diagnosis"] = (
            "AWS Seoul에서 "
            "AION2 공식 API 정상 응답"
        )

    else:

        result["diagnosis"] = (
            "AION2 공식 API가 "
            "빈 응답 또는 제한됨"
        )


    return result


# ============================================================
# 메인 페이지
# ============================================================

@app.route("/")
def home():

    return jsonify({
        "status": "ok",
        "service": "AION2 Legion API",
        "message": "서버가 정상 실행 중입니다.",
        "testUrl": "/test",
        "characterExample":
            "/character?name=갹&serverId=2012&race=2"
    })


# ============================================================
# 고정 테스트
#
# 갹 / 울고른 / 마족
# ============================================================

@app.route("/test")
def test():

    result = get_character_data(
        DEFAULT_NAME,
        DEFAULT_SERVER_ID,
        DEFAULT_RACE
    )

    status_code = (
        200
        if result.get("success")
        else 502
    )

    return jsonify(
        result
    ), status_code


# ============================================================
# 실제 캐릭터 조회
#
# 예:
# /character?name=갹&serverId=2012&race=2
# ============================================================

@app.route("/character")
def character():

    name = str(
        request.args.get(
            "name",
            ""
        )
    ).strip()


    server_id_text = str(
        request.args.get(
            "serverId",
            ""
        )
    ).strip()


    race_text = str(
        request.args.get(
            "race",
            ""
        )
    ).strip()


    if not name:

        return jsonify({
            "success": False,
            "error": "name 값이 필요합니다."
        }), 400


    try:

        server_id = int(
            server_id_text
        )

    except Exception:

        return jsonify({
            "success": False,
            "error": (
                "serverId가 올바르지 않습니다."
            )
        }), 400


    # race 값을 생략한 경우
    # 1000번대 = 천족
    # 2000번대 = 마족
    if race_text:

        try:

            race = int(
                race_text
            )

        except Exception:

            return jsonify({
                "success": False,
                "error": (
                    "race가 올바르지 않습니다."
                )
            }), 400

    else:

        if (
            1000 <= server_id < 2000
        ):

            race = 1

        elif (
            2000 <= server_id < 3000
        ):

            race = 2

        else:

            return jsonify({
                "success": False,
                "error": (
                    "서버 ID로 종족을 "
                    "판별할 수 없습니다."
                )
            }), 400


    result = get_character_data(
        name,
        server_id,
        race
    )


    status_code = (
        200
        if result.get("success")
        else 502
    )


    return jsonify(
        result
    ), status_code


# ============================================================
# 헬스 체크
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "ok": True
    })


# ============================================================
# 로컬 직접 실행
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
