from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import os
import re
from urllib.parse import unquote

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)
app.json.ensure_ascii = False


BASE_URL = "https://aion2.plaync.com"

API_KEY = os.environ.get(
    "AION2_API_KEY",
    ""
).strip()

MAX_BATCH = 150
MAX_WORKERS = 4
TIMEOUT = 15


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)


# ============================================================
# 이름 정리
# ============================================================

def clean_name(value):

    value = re.sub(
        r"<[^>]+>",
        "",
        str(value or "")
    )

    return html.unescape(
        value
    ).strip()


# ============================================================
# 서버 ID -> 종족
# ============================================================

def infer_race(server_id):

    server_id = int(
        server_id
    )

    if 1000 <= server_id < 2000:
        return 1

    if 2000 <= server_id < 3000:
        return 2

    raise ValueError(
        f"서버 ID로 종족을 판별할 수 없습니다: {server_id}"
    )


# ============================================================
# NC 요청 헤더
# ============================================================

def make_headers(referer=None):

    headers = {

        "User-Agent":
            USER_AGENT,

        "Accept":
            "application/json, text/plain, */*",

        "Accept-Language":
            "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    if referer:

        headers["Referer"] = (
            referer
        )

    return headers


# ============================================================
# 아이템레벨 추출
# ============================================================

def find_item_level(info):

    stat_list = (
        (info.get("stat") or {})
        .get("statList")
        or []
    )

    for item in stat_list:

        if not isinstance(
            item,
            dict
        ):
            continue

        if (
            item.get("type") == "ItemLevel"
            or
            item.get("name") == "아이템레벨"
        ):
            return item.get(
                "value"
            )

    return None


# ============================================================
# API KEY 확인
#
# Cloudtype 환경변수 AION2_API_KEY가 비어 있으면
# 인증 없이 사용
# ============================================================

def authorized():

    if not API_KEY:
        return True

    return (
        request.headers.get(
            "X-API-Key",
            ""
        )
        == API_KEY
    )


# ============================================================
# 캐릭터 조회
# ============================================================

def lookup_character(
    name,
    server_id
):

    name = str(
        name or ""
    ).strip()

    server_id = int(
        server_id
    )

    if not name:

        return {

            "success": False,

            "name":
                name,

            "serverId":
                server_id,

            "error":
                "캐릭터명이 비어 있습니다."
        }


    try:

        race = infer_race(
            server_id
        )

        session = (
            requests.Session()
        )


        # ====================================================
        # 1. 캐릭터 검색
        # ====================================================

        search_response = session.get(

            BASE_URL
            + "/ko-kr/api/search/aion2/search/v2/character",

            params={
                "keyword":
                    name,

                "race":
                    race,

                "serverId":
                    server_id,

                "page":
                    1,

                "size":
                    40
            },

            headers=
                make_headers(
                    BASE_URL
                    + "/ko-kr/"
                ),

            timeout=
                TIMEOUT
        )


        search_response.raise_for_status()


        search_json = (
            search_response.json()
        )


        exact = None


        for item in search_json.get(
            "list",
            []
        ):

            found_name = clean_name(
                item.get("name")
            )


            if found_name == name:

                exact = item
                break


        if (
            not exact
            or
            not exact.get(
                "characterId"
            )
        ):

            return {

                "success":
                    False,

                "name":
                    name,

                "serverId":
                    server_id,

                "error":
                    "정확히 일치하는 캐릭터를 찾지 못했습니다."
            }


        character_id = unquote(
            str(
                exact.get(
                    "characterId"
                )
            )
        )


        # ====================================================
        # 2. 상세정보
        # ====================================================

        info_response = session.get(

            BASE_URL
            + "/api/character/info",

            params={

                "lang":
                    "ko",

                "characterId":
                    character_id,

                "serverId":
                    server_id
            },

            headers=
                make_headers(
                    BASE_URL
                    + "/ko-kr/"
                ),

            timeout=
                TIMEOUT
        )


        info_response.raise_for_status()


        info = (
            info_response.json()
        )


        if (
            not isinstance(
                info,
                dict
            )
            or
            not info
        ):

            return {

                "success":
                    False,

                "name":
                    name,

                "serverId":
                    server_id,

                "error":
                    "AION2 상세 API가 빈 응답을 반환했습니다."
            }


        profile = (
            info.get(
                "profile"
            )
            or {}
        )


        return {

            "success":
                True,

            "name":
                profile.get(
                    "characterName"
                )
                or name,

            "className":
                profile.get(
                    "className"
                )
                or "",

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
                )
                or "",

            "serverId":
                profile.get(
                    "serverId"
                )
                or server_id,

            "serverName":
                profile.get(
                    "serverName"
                )
                or exact.get(
                    "serverName"
                )
                or "",

            "regionName":
                profile.get(
                    "regionName"
                )
                or "",

            "profileImage":
                profile.get(
                    "profileImage"
                )
                or ""
        }


    except Exception as exc:

        return {

            "success":
                False,

            "name":
                name,

            "serverId":
                server_id,

            "error":
                str(exc)
        }


# ============================================================
# 인증
# ============================================================

@app.before_request
def check_api_key():

    if request.path == "/":

        return None


    if not authorized():

        return jsonify({

            "success":
                False,

            "error":
                "Unauthorized"

        }), 401


    return None


# ============================================================
# 서버 상태
# ============================================================

@app.get("/")
def home():

    return jsonify({

        "status":
            "ok",

        "service":
            "AION2 Legion API"
    })


# ============================================================
# 캐릭터 1명 조회
#
# /character?name=갹&serverId=2012
# ============================================================

@app.get("/character")
def character():

    name = request.args.get(
        "name",
        ""
    ).strip()


    server_id = request.args.get(
        "serverId",
        ""
    ).strip()


    if (
        not name
        or
        not server_id
    ):

        return jsonify({

            "success":
                False,

            "error":
                "name과 serverId가 필요합니다."

        }), 400


    try:

        result = lookup_character(

            name,

            int(
                server_id
            )
        )


    except ValueError:

        return jsonify({

            "success":
                False,

            "error":
                "serverId가 올바르지 않습니다."

        }), 400


    return jsonify(
        result
    ), (
        200
        if result.get(
            "success"
        )
        else 404
    )


# ============================================================
# 여러 캐릭터 일괄 조회
#
# POST /batch
#
# {
#   "characters": [
#     {"name":"갹","serverId":2012}
#   ]
# }
# ============================================================

@app.post("/batch")
def batch():

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )


    characters = (
        body.get(
            "characters"
        )
        or []
    )


    if not isinstance(
        characters,
        list
    ):

        return jsonify({

            "success":
                False,

            "error":
                "characters는 배열이어야 합니다."

        }), 400


    if (
        len(
            characters
        )
        > MAX_BATCH
    ):

        return jsonify({

            "success":
                False,

            "error":
                f"한 번에 최대 {MAX_BATCH}명까지 조회할 수 있습니다."

        }), 400


    jobs = []


    for index, item in enumerate(
        characters
    ):

        if not isinstance(
            item,
            dict
        ):
            continue


        name = str(
            item.get(
                "name"
            )
            or ""
        ).strip()


        server_id = item.get(
            "serverId"
        )


        if (
            not name
            or
            server_id is None
        ):
            continue


        try:

            jobs.append((

                index,

                name,

                int(
                    server_id
                )
            ))


        except (
            TypeError,
            ValueError
        ):

            continue


    results_by_index = {}


    with ThreadPoolExecutor(
        max_workers=
            MAX_WORKERS
    ) as executor:


        future_map = {

            executor.submit(

                lookup_character,

                name,

                server_id

            ): index

            for (
                index,
                name,
                server_id
            )
            in jobs
        }


        for future in as_completed(
            future_map
        ):

            index = (
                future_map[
                    future
                ]
            )


            try:

                results_by_index[
                    index
                ] = (
                    future.result()
                )


            except Exception as exc:

                results_by_index[
                    index
                ] = {

                    "success":
                        False,

                    "error":
                        str(exc)
                }


    results = [

        results_by_index[
            index
        ]

        for (
            index,
            _,
            _
        )
        in jobs

        if index
        in results_by_index
    ]


    return jsonify({

        "success":
            True,

        "count":
            len(
                results
            ),

        "results":
            results
    })


# ============================================================
# 직접 실행
# ============================================================

if __name__ == "__main__":

    app.run(

        host=
            "0.0.0.0",

        port=
            5000
    )
