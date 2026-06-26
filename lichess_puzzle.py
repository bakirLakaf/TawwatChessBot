# -*- coding: utf-8 -*-
"""
جلب «لغز اليوم» من Lichess (مجاني، موثّق) وتحويله إلى:
- وضعية FEN لرسم الرقعة
- من يلعب (الأبيض/الأسود)
- الحل بصيغة مقروءة (للتعليق الأول)
لا نخترع ألغازًا أبدًا — كلها من قاعدة Lichess المُتحقَّقة.
"""
import io
import logging
import requests
import chess
import chess.pgn

log = logging.getLogger(__name__)
DAILY_URL = "https://lichess.org/api/puzzle/daily"
NEXT_URL = "https://lichess.org/api/puzzle/next"

# تحيّز صعوبة Lichess حسب المستوى المطلوب (نسبيّ)
_DIFF_PARAM = {"medium": "normal", "hard": "hardest"}


def _reach_position(game, init_ply, first_move):
    """يبني وضعية اللغز: بعد initialPly+1 نقلة (اصطلاح Lichess)، مع تصحيح احتياطي."""
    moves = list(game.mainline_moves())
    for target in (init_ply + 1, init_ply):       # +1 هو الصحيح؛ السابق احتياط
        b = game.board()
        for mv in moves[:target]:
            b.push(mv)
        if first_move in b.legal_moves:
            return b
    return None


def _parse(data):
    """يحوّل رد Lichess إلى dict: fen, turn, solution, id, rating, themes."""
    game = chess.pgn.read_game(io.StringIO(data["game"]["pgn"]))
    if game is None:
        return None
    init_ply = int(data["puzzle"]["initialPly"])
    solution_uci = data["puzzle"]["solution"]
    first = chess.Move.from_uci(solution_uci[0])
    board = _reach_position(game, init_ply, first)
    if board is None:
        return None
    fen = board.fen()
    turn = "الأبيض" if board.turn else "الأسود"
    san, b2 = [], board.copy()
    for uci in solution_uci:
        mv = chess.Move.from_uci(uci)
        san.append(b2.san(mv)); b2.push(mv)
    return {"fen": fen, "turn": turn, "solution": " ".join(san),
            "id": data["puzzle"]["id"], "rating": data["puzzle"].get("rating"),
            "themes": data["puzzle"].get("themes", [])}


def _fetch(url):
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "TawwatChessBot"})
        if r.status_code != 200:
            log.warning("Lichess أرجع رمز %s", r.status_code)
            return None
        return _parse(r.json())
    except Exception as e:
        log.warning("تعذّر جلب/تحليل لغز Lichess: %s", e)
        return None


def get_daily_puzzle():
    """لغز اليوم من Lichess (يبقى للتوافق)."""
    return _fetch(DAILY_URL)


def get_puzzle(difficulty=None):
    """لغز عشوائي من Lichess. difficulty: 'medium' أو 'hard' (أو None لعشوائي)."""
    url = NEXT_URL
    param = _DIFF_PARAM.get(difficulty or "")
    if param:
        url += f"?difficulty={param}"
    return _fetch(url)
