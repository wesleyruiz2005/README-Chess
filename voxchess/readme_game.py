"""Community README chess, rendered with voxchess.

A GitHub Action opens on every issue titled `Chess: ...`, this module validates
the move, animates it as an isometric voxel GIF (instead of a table of flat
piece images) and rewrites the board section of the README in place.

Run by the Action as `python -m voxchess.readme_game`. Run locally with
`--demo` to render a sample move GIF without touching GitHub.
"""
from __future__ import annotations
import ast
import os
import re
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from urllib.parse import urlencode

import chess
import chess.pgn

from . import vox
from .animate import MoveAnim, animate_move
from .board import BoardLayout, parse_fen
from .color import Palette
from .render_png import Effects, Scene, upscale
from .animate import save_gif

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
README = ROOT / "README.md"
IMAGES = ROOT / "images"
DATA = ROOT / "data"
GAMES = ROOT / "games"
BOARD_GIF = IMAGES / "chess.gif"          # embedded in the README

# Config that used to live in settings.yaml, inlined to drop the PyYAML dep.
SETTINGS = {
    "comments": {
        "consecutive_moves": "Sorry {author}, you can't move twice in a row! "
                             "You can ask someone to play the next turn :D",
        "game_over": "And that's a game over! {outcome}! This game had {num_moves} "
                     "moves made by {num_players} players.\n\nThanks to {players} "
                     "for participating!",
        "invalid_board": "{author} Sorry, I can't perform the specified move. "
                         "The board is invalid!",
        "invalid_move": "{author} Whaaaat? The move `{move}` is invalid!\nMaybe "
                        "someone squeezed a move before you. Please try again.",
        "invalid_new_game": "{author} Sorry, but you cannot start a new game while "
                            "the old one is still in progress. Only the repo owner "
                            "can do that.",
        "successful_move": "{author} done! Successfully played move `{move}` for "
                           "current game.\nThanks for playing!",
        "successful_new_game": "{author} done! New game successfully started!",
        "unknown_command": "{author} Sorry, I can't understand the command. Please "
                           "try again and do not modify the issue title!",
    },
    "issues": {
        "link": "https://github.com/{repo}/issues/new?{params}",
        "move": {"body": 'Please do not change the title. Just click "Submit new '
                         'issue". You don\'t need to do anything else :D',
                 "title": "Chess: Move {source} to {dest}"},
        "new_game": {"body": 'Please do not change the title. Just click "Submit '
                             'new issue". You don\'t need to do anything else :D',
                     "title": "Chess: Start new game"},
    },
    "markers": {
        "board":      {"begin": "<!-- BEGIN CHESS BOARD -->\n", "end": "<!-- END CHESS BOARD -->\n"},
        "moves":      {"begin": "<!-- BEGIN MOVES LIST -->\n",  "end": "<!-- END MOVES LIST -->\n"},
        "turn":       {"begin": "<!-- BEGIN TURN -->",          "end": "<!-- END TURN -->"},
        "last_moves": {"begin": "<!-- BEGIN LAST MOVES -->\n",  "end": "<!-- END LAST MOVES -->\n"},
        "top_moves":  {"begin": "<!-- BEGIN TOP MOVES -->\n",   "end": "<!-- END TOP MOVES -->\n"},
    },
    "misc": {"max_last_moves": 5, "max_top_moves": 10},
}


class Action(Enum):
    UNKNOWN = 0
    MOVE = 1
    NEW_GAME = 2


# ------------------------------------------------------------- voxel render
_MODELS_CACHE = None


def _scene():
    global _MODELS_CACHE
    if _MODELS_CACHE is None:
        _MODELS_CACHE = vox.load_set(MODELS)
    m = _MODELS_CACHE
    layout = BoardLayout(voxel=4, square=14, frame=3, slab=4,
                         piece_size=max(g.shape[0] for g in m.values()))
    # ponytail: grain off keeps the per-frame dither loop cheap in CI; a full
    # 16-frame board GIF is ~15s. Drop frames or voxel width if that grows.
    return m, Scene(layout, Palette("magenta", "8bit"), m, "solid", Effects(grain=False))


def render_move_gif(fen_before: str, frm: str, to: str, scale: int = 2) -> None:
    """Animate the move over the position BEFORE it was played and save the GIF."""
    m, scene = _scene()
    frames, durs = animate_move(scene, parse_fen(fen_before), frm, to,
                                anim=MoveAnim(frames=16), scale=scale)
    IMAGES.mkdir(exist_ok=True)
    save_gif(BOARD_GIF, frames, durs)


def render_board_gif(fen: str, scale: int = 2) -> None:
    """Single static frame of a position (new game / no move to animate)."""
    m, scene = _scene()
    img = upscale(scene.render(parse_fen(fen)), scale)
    IMAGES.mkdir(exist_ok=True)
    save_gif(BOARD_GIF, [img], [1000])


def _board_embed() -> str:
    rel = BOARD_GIF.relative_to(ROOT).as_posix()
    return f'<p align="center"><img src="{rel}" alt="voxel chess board" width="520"></p>\n'


# ----------------------------------------------------------------- state io
def update_top_moves(user: str) -> None:
    path = DATA / "top_moves.txt"
    dictionary = ast.literal_eval(path.read_text()) if path.exists() else {}
    dictionary[user] = dictionary.get(user, 0) + 1
    path.write_text(str(dictionary))


def update_last_moves(line: str) -> None:
    path = DATA / "last_moves.txt"
    content = path.read_text() if path.exists() else ""
    path.write_text(line.rstrip("\r\n") + "\n" + content)


def replace_text_between(text: str, marker: dict, replacement: str) -> str:
    a, b = marker["begin"], marker["end"]
    if text.find(a) == -1 or text.find(b) == -1:
        return text
    return text.split(a)[0] + a + replacement + b + text.split(b)[1]


# ------------------------------------------------------------- markdown bits
def _create_link(text, link):
    return f"[{text}]({link})"


def _issue_link(source, dest_list):
    link = SETTINGS["issues"]["link"].format(
        repo=os.environ["GITHUB_REPOSITORY"],
        params=urlencode(SETTINGS["issues"]["move"], safe="{}"))
    return ", ".join(_create_link(d, link.format(source=source, dest=d))
                     for d in sorted(dest_list))


def generate_moves_list(board) -> str:
    if board.is_game_over():
        link = SETTINGS["issues"]["link"].format(
            repo=os.environ["GITHUB_REPOSITORY"],
            params=urlencode(SETTINGS["issues"]["new_game"]))
        return "**GAME IS OVER!** " + _create_link("Click here", link) + " to start a new game :D\n"

    from collections import defaultdict
    moves = defaultdict(set)
    for mv in board.legal_moves:
        moves[chess.SQUARE_NAMES[mv.from_square].upper()].add(
            chess.SQUARE_NAMES[mv.to_square].upper())

    md = "**CHECK!** Choose your move wisely!\n" if board.is_check() else ""
    md += "|  FROM  | TO (Just click a link!) |\n| :----: | :---------------------- |\n"
    for source, dest in sorted(moves.items()):
        md += f"| **{source}** | {_issue_link(source, dest)} |\n"
    return md


def generate_last_moves() -> str:
    path = DATA / "last_moves.txt"
    md = "\n| Move | Author |\n| :--: | :----- |\n"
    if path.exists():
        for i, line in enumerate(path.read_text().splitlines()):
            if ":" not in line or i >= SETTINGS["misc"]["max_last_moves"]:
                break
            parts = line.rstrip().split(":")
            author = _create_link(parts[1], "https://github.com/" + parts[1].lstrip()[1:])
            m = re.search("([A-H][1-8])([A-H][1-8])", line, re.I)
            if m:
                md += f"| `{m.group(1).upper()}` to `{m.group(2).upper()}` | {author} |\n"
            else:
                md += f"| `{parts[0]}` | {author} |\n"
    return md + "\n"


def generate_top_moves() -> str:
    path = DATA / "top_moves.txt"
    dictionary = ast.literal_eval(path.read_text()) if path.exists() else {}
    md = "\n| Total moves |  User  |\n| :---------: | :----- |\n"
    for key, val in sorted(dictionary.items(), key=lambda x: x[1], reverse=True)[
            :SETTINGS["misc"]["max_top_moves"]]:
        md += f"| {val} | {_create_link(key, 'https://github.com/' + key[1:])} |\n"
    return md + "\n"


# --------------------------------------------------------------- issue parse
def parse_issue(title: str):
    if title.lower() == "chess: start new game":
        return (Action.NEW_GAME, None)
    if "chess: move" in title.lower():
        m = re.match("Chess: Move ([A-H][1-8]) to ([A-H][1-8])", title, re.I)
        return (Action.MOVE, (m.group(1) + m.group(2)).lower())
    return (Action.UNKNOWN, None)


# ---------------------------------------------------------------------- main
def main(issue, issue_author, repo_owner):
    action = parse_issue(issue.title)
    gameboard = chess.Board()
    C = SETTINGS["comments"]
    current = GAMES / "current.pgn"

    if action[0] == Action.NEW_GAME:
        if current.exists() and issue_author != repo_owner:
            issue.create_comment(C["invalid_new_game"].format(author=issue_author))
            issue.edit(state="closed")
            return False, "ERROR: A game is in progress. Only the repo owner can start a new game"

        issue.create_comment(C["successful_new_game"].format(author=issue_author))
        issue.edit(state="closed")
        DATA.mkdir(exist_ok=True)
        (DATA / "last_moves.txt").write_text("Start game: " + issue_author)

        game = chess.pgn.Game()
        game.headers["Event"] = repo_owner + "'s Online Open Chess Tournament"
        game.headers["Site"] = "https://github.com/" + os.environ["GITHUB_REPOSITORY"]
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        game.headers["Round"] = "1"
        render_board_gif(gameboard.fen())

    elif action[0] == Action.MOVE:
        if not current.exists():
            return False, "ERROR: There is no game in progress! Start a new game first"

        with open(current) as f:
            game = chess.pgn.read_game(f)
            gameboard = game.board()
        for mv in game.mainline_moves():
            gameboard.push(mv)

        line = (DATA / "last_moves.txt").read_text().splitlines()[0]
        last_player, last_move = line.split(":")[1].strip(), line.split(":")[0].strip()

        if action[1][:2] == action[1][2:]:
            issue.create_comment(C["invalid_move"].format(author=issue_author, move=action[1]))
            issue.edit(state="closed", labels=["Invalid"])
            return False, "ERROR: Move is invalid!"

        if chess.Move.from_uci(action[1] + "q") in gameboard.legal_moves:
            action = (action[0], action[1] + "q")           # auto-promote to queen
        move = chess.Move.from_uci(action[1])

        if last_player == issue_author and "Start game" not in last_move:
            issue.create_comment(C["consecutive_moves"].format(author=issue_author))
            issue.edit(state="closed", labels=["Invalid"])
            return False, "ERROR: Two moves in a row!"
        if move not in gameboard.legal_moves:
            issue.create_comment(C["invalid_move"].format(author=issue_author, move=action[1]))
            issue.edit(state="closed", labels=["Invalid"])
            return False, "ERROR: Move is invalid!"
        if not gameboard.is_valid():
            issue.create_comment(C["invalid_board"].format(author=issue_author))
            issue.edit(state="closed", labels=["Invalid"])
            return False, "ERROR: Board is invalid!"

        labels = ["⚔️ Capture!"] if gameboard.is_capture(move) else []
        labels += ["White(clear)" if gameboard.turn == chess.WHITE else "Black(solid)"]
        issue.create_comment(C["successful_move"].format(author=issue_author, move=action[1]))
        issue.edit(state="closed", labels=labels)

        update_last_moves(action[1] + ": " + issue_author)
        update_top_moves(issue_author)

        # animate this move over the position it was played FROM, then commit it
        render_move_gif(gameboard.fen(), action[1][:2], action[1][2:4])
        gameboard.push(move)
        game.end().add_main_variation(move, comment=issue_author)
        game.headers["Result"] = gameboard.result()

    else:
        issue.create_comment(C["unknown_command"].format(author=issue_author))
        issue.edit(state="closed", labels=["Invalid"])
        return False, "ERROR: Unknown action"

    GAMES.mkdir(exist_ok=True)
    print(game, file=open(current, "w"), end="\n\n")

    if gameboard.is_game_over():
        outcome = {"1/2-1/2": "It's a draw", "1-0": "White(clear) wins",
                   "0-1": "Black(solid) wins"}.get(gameboard.result(), "UNKNOWN")
        lines = (DATA / "last_moves.txt").read_text().splitlines()
        pattern = re.compile(r".*: (@[a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38})", re.I)
        players = {re.match(pattern, ln).group(1) for ln in lines if re.match(pattern, ln)}
        issue.add_to_labels("👑 Draw!" if gameboard.result() == "1/2-1/2" else "👑 Winner!")
        issue.create_comment(C["game_over"].format(
            outcome=outcome, players=", ".join(players),
            num_moves=len(lines) - 1, num_players=len(players)))
        current.rename(GAMES / datetime.now().strftime("game-%Y%m%d-%H%M%S.pgn"))
        (DATA / "last_moves.txt").unlink(missing_ok=True)

    readme = README.read_text(encoding="utf-8")
    M = SETTINGS["markers"]
    readme = replace_text_between(readme, M["board"], _board_embed())
    readme = replace_text_between(readme, M["moves"], generate_moves_list(gameboard))
    readme = replace_text_between(readme, M["turn"],
                                  "white(clear)" if gameboard.turn == chess.WHITE else "black(solid)")
    readme = replace_text_between(readme, M["last_moves"], generate_last_moves())
    readme = replace_text_between(readme, M["top_moves"], generate_top_moves())
    README.write_text(readme, encoding="utf-8")
    return True, ""


def demo():
    """Render a sample opening move GIF locally (no GitHub). Self-check."""
    b = chess.Board()
    b.push_uci("e2e4"); b.push_uci("e7e5")
    render_move_gif(b.fen(), "g1", "f3")
    assert BOARD_GIF.exists() and BOARD_GIF.stat().st_size > 0, "GIF was not written"
    print("demo ok ->", BOARD_GIF)


if __name__ == "__main__":
    if "--demo" in sys.argv or "GITHUB_TOKEN" not in os.environ:
        demo()
        sys.exit(0)
    from github import Github
    repo = Github(os.environ["GITHUB_TOKEN"]).get_repo(os.environ["GITHUB_REPOSITORY"])
    issue = repo.get_issue(number=int(os.environ["ISSUE_NUMBER"]))
    ret, reason = main(issue, "@" + issue.user.login, "@" + os.environ["REPOSITORY_OWNER"])
    if ret is False:
        sys.exit(reason)
