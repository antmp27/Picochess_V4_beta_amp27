#!/usr/bin/env python3

# Copyright (C) 2013-2019 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#                         Molli (and thanks to Martin  for his opening
#                         identification code)
#                         Johan Sjöblom
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import csv
import logging
from random import randint
from typing import Tuple
import platform
import asyncio
import chess  # type: ignore
from chess.engine import InfoDict, Limit
import chess.engine
import chess.pgn
from uci.engine import UciShell, UciEngine
from dgt.util import PicoComment, PicoCoach

# PicoTutor Constants
import picotutor_constants as c

logger = logging.getLogger(__name__)


class PicoTutor:
    def __init__(
        self,
        i_ucishell: UciShell,
        i_engine_path="/opt/picochess/engines/aarch64/a-stockf",
        i_player_color=chess.WHITE,
        i_fen="",
        i_comment_file="",
        i_lang="en",
        i_always_run_tutor=False,
        loop=None,
    ):
        self.user_color: chess.Color = i_player_color
        self.engine_path: str = i_engine_path

        self.best_engine: UciEngine | None = None  # best - max
        self.obvious_engine: UciEngine | None = None  # obvious - min
        # snapshot list of best = deep/max-ply, and obvious = shallow/low-ply
        # lists of InfoDict per color - filled in eval_legal_moves()
        self.best_info = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_info = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # snapshot of best_moves and obvious_moves are filled in _eval_pv_list()
        # information comes from InfoDict snapshot lists above: best_info and obvious_info
        # "almost" complete 5-50 list of tuple(pv_key, move, score, mate)
        self.best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # history list of user move selected from best_moves and obvious_moves above
        # tuple(pv_key, move, score, mate) copy for selected user move
        # pv_key is the index to the snapshot best_info and obvious_info
        # index = None indicates was not found in InfoDict results
        # index not None has no value in history as its an index to a snapshot above
        self.best_history = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_history = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # pv_user_move and pv_best_move are the pv array from InfoDict analysis
        self.pv_user_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.pv_best_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.hint_move = {color: chess.Move.null() for color in [chess.WHITE, chess.BLACK]}
        self.op = []  # used for opening book
        self.last_inside_book_moveno = 0
        # alt_best_moves are filled in eval_legal_moves()
        self.alt_best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.comments = []
        self.comment_no = 0
        self.comments_all = []
        self.comment_all_no = 0
        self.lang = i_lang
        self.expl_start_position = True
        self.watcher_on = False
        self.coach_on = False
        self.explorer_on = False
        self.comments_on = False
        self.mame_par = ""  # @todo create this info?
        # one of the challenges is to keep this board in sync
        # with the state.game board in picochess.py main
        self.board = chess.Board()
        self.ucishell = i_ucishell
        self.loop = loop  # main loop everywhere
        self.deep_limit_depth = None  # override picotutor value in set_mode
        # evaluated moves keeps a memory of all non zero evaluation strings
        # it can then be used to print comments in the PGN file
        self.evaluated_moves = {}  # key=(fullmove_number, turn, move) value={}
        # the following setting can be True if engine is not playing
        # or if you want to analyse also engine moves (like pgn_engine)
        self.analyse_both_sides = False  # analyse only user side as default
        self.always_run_tutor = i_always_run_tutor  # force deep tutor to always run
        # new feature to be able to step through a PGN game
        self.pgn_game: chess.pgn.Game | None = None

        try:
            with open("chess-eco_pos.txt") as fp:
                self.book_data = list(csv.DictReader(filter(lambda row: row[0] != "#", fp.readlines()), delimiter="|"))
        except EnvironmentError:
            self.book_data = []

        try:
            with open("opening_name_fen.txt") as fp:
                self.book_fen_data = fp.readlines()
        except FileNotFoundError:
            self.book_fen_data = []

        self._setup_comments(i_lang, i_comment_file)

        self._setup_board(i_fen)

    def set_pgn_game_to_step(self, pgn_game: chess.pgn.Game):
        """store a loaded PGN game here so that it can be stepped through"""
        self.pgn_game = pgn_game  # read by picochess.py read_pgn_file()

    def get_next_pgn_move(self, current_board: chess.Board) -> chess.Move:
        """whats the next move to step through in a loaded PGN game
        send current game board to see if a match is found in the loaded PGN game
        return None if no PGN file loaded or PGN move not found"""
        if self.pgn_game:
            node = self.pgn_game
            # special case - starting position
            if current_board.fen() == chess.Board.starting_fen:
                if node.variations:
                    return node.variations[0].move  # Return the first move
                else:
                    return None  # special case, PGN game had no moves at all
            while node.variations:
                next_node = node.variations[0]
                # Apply the current move to a temporary board
                temp_board = node.board()
                temp_board.push(next_node.move)

                if temp_board.fen() == current_board.fen():
                    # This board is the current one; return the next move from here
                    if next_node.variations:
                        return next_node.variations[0].move  # Return the next move
                    else:
                        return None  # No move after this
                node = next_node
        return None  # Reached end of game without matching board

    async def open_engine(self):
        """open the tutor engine"""
        # @todo we have to start the engine always as the set_status has
        # not yet been changed to async --> causes changes in main
        # set_status might later be changed that require this engine
        if not self.best_engine:
            options = {"MultiPV": c.VALID_ROOT_MOVES, "Contempt": 0, "Threads": c.NUM_THREADS}
            self.best_engine = await self._load_engine(options, "best picotutor")
            if self.best_engine is None:
                logger.debug("best engine loading failed in Picotutor")
        if not self.obvious_engine:
            options = {"MultiPV": c.VALID_ROOT_MOVES, "Contempt": 0, "Threads": c.LOW_NUM_THREADS}
            self.obvious_engine = await self._load_engine(options, "obvious picotutor")
            if self.obvious_engine is None:
                logger.debug("obvious engine loading failed in Picotutor")

    async def _load_engine(self, options: dict, debug_whoami: str) -> UciEngine:
        """internal function to load each tutor engine"""
        engine = UciEngine(self.engine_path, self.ucishell, self.mame_par, self.loop, debug_whoami)
        await engine.open_engine()
        if engine.loaded_ok() is True:
            await engine.startup(options=options)
            engine.set_mode()  # not needed as we dont ponder?
        else:
            engine = None
        return engine

    def get_eng_long_name(self):
        """return the full engine name as used by picotutor"""
        return self.best_engine.get_long_name() if self.best_engine else "no engine"

    async def set_mode(self, analyse_both_sides: bool, deep_limit_depth: int = None):
        """normally analyse_both_sides is False but if True both sides will be analysed
        deep_limit_depth defaults to DEEP_DEPTH 17 if not set"""
        self.deep_limit_depth = deep_limit_depth  # None also ok = back to default
        if self.analyse_both_sides != analyse_both_sides:
            self.analyse_both_sides = analyse_both_sides
            await self._start_or_stop_as_needed()

    def can_use_coach_analyser(self) -> bool:
        """is the tutor active and analysing, and has user turned on the watcher
        - if yes InfoDicts can be used"""
        result = False
        # most analysing functions are skipped if neither coach nor watcher is on
        # in this case its enough if watcher is on - coach can be off
        if self.best_engine:
            if self.best_engine.loaded_ok() and self.watcher_on:  # coach can be off
                result = self.best_engine.is_analyser_running()
        return result

    def _setup_comments(self, i_lang, i_comment_file):
        if i_comment_file:
            try:
                with open(i_comment_file) as fp:
                    self.comments = fp.readlines()
            except OSError:
                self.comments = []

            if self.comments:
                self.comment_no = len(self.comments)

        try:
            arch = platform.machine()
            general_comment_file = "/opt/picochess/engines/" + arch + "/general_game_comments_" + i_lang + ".txt"
            with open(general_comment_file) as fp:
                self.comments_all = fp.readlines()
        except (OSError, IOError):
            self.comments_all = []

        if self.comments_all:
            self.comment_all_no = len(self.comments_all)

    def _setup_board(self, i_fen):
        if i_fen:
            self.board = chess.Board(i_fen)
        else:
            self.board = chess.Board()  # starting position if no other set_position command comes

    async def set_status(self, watcher=False, coach=PicoCoach.COACH_OFF, explorer=False, comments=False):
        if coach == PicoCoach.COACH_OFF:
            b_coach = False
        else:
            b_coach = True

        self.watcher_on = watcher
        self.coach_on = b_coach
        self.explorer_on = explorer
        self.comments_on = comments
        # @ todo - check if something changed before calling
        await self._start_or_stop_as_needed()

    def get_game_comment(self, pico_comment=PicoComment.COM_OFF, com_factor=0):
        max_range = 0
        max_range_all = 0
        range_fac = 0

        if com_factor == 0:
            return ""
        range_fac = round(100 / com_factor)
        max_range = self.comment_no * range_fac
        max_range_all = self.comment_all_no * range_fac

        if pico_comment == PicoComment.COM_ON_ENG:
            # get a comment by pure chance
            if self.comments and self.comment_no > 0:
                index = randint(0, max_range)
                if index > self.comment_no - 1:
                    return ""
                return self.comments[index]
            else:
                return ""
        elif pico_comment == PicoComment.COM_ON_ALL:
            # get a comment by pure chance
            if self.comments and self.comment_no > 0:
                index = randint(0, max_range)
                if index > self.comment_no - 1:
                    return ""
                return self.comments[index]
            else:
                if self.comments_all and self.comment_all_no > 0:
                    index = randint(0, max_range_all)
                    if index > self.comment_all_no - 1:
                        return ""
                    return self.comments_all[index]
                else:
                    return ""

    def init_comments(self, i_comment_file):
        self.comments = []
        self.comment_no = 0
        if i_comment_file:
            try:
                self.comments = open(i_comment_file).readlines()
            except OSError:
                self.comments = []

            if self.comments:
                self.comment_no = len(self.comments)

        else:
            self.comments = []

    def _find_longest_matching_opening(self, played: str) -> Tuple[str, str, str]:
        opening_name = moves = eco = ""
        for opening in self.book_data:
            # if len(opening.get('moves')) > 5:
            if played[: len(opening.get("moves"))] == opening.get("moves"):
                if len(opening.get("moves")) > len(moves):
                    opening_name = opening.get("opening_name")
                    moves = opening.get("moves")
                    eco = opening.get("eco")
        return opening_name, moves, eco

    def get_opening(self) -> Tuple[str, str, str, bool]:
        # check if game started really from start position
        # (otherwise we can't use opening based on just the moves)

        halfmoves = 2 * self.board.fullmove_number
        if self.board.turn:
            halfmoves -= 2
        else:
            halfmoves -= 1

        diff = self.board.fullmove_number - self.last_inside_book_moveno
        inside_book_opening = False

        opening_name = moves = eco = ""

        if self.op == [] or diff > 2:
            return eco, opening_name, moves, inside_book_opening

        played = "%s" % (" ".join(self.op))

        opening_name, moves, eco = self._find_longest_matching_opening(played)

        if self.expl_start_position and halfmoves <= len(moves.split()):
            inside_book_opening = True
            self.last_inside_book_moveno = self.board.fullmove_number
        else:
            # try opening name based on FEN
            op_name = ""
            i_book = False

            op_name, i_book = self.get_fen_opening()
            if i_book and op_name:
                opening_name = op_name
                inside_book_opening = True
                self.last_inside_book_moveno = self.board.fullmove_number
            else:
                inside_book_opening = False

        return eco, opening_name, moves, inside_book_opening

    def get_fen_opening(self):
        fen = self.board.board_fen()

        if not fen:
            return "", False

        index = 0
        opening_name = ""

        for line in self.book_fen_data:
            line_list = line.split()
            if line_list[0] == fen:
                opening_name = self.book_fen_data[index + 1]
                break
            index = index + 1

        if opening_name:
            return opening_name, True
        else:
            return "", False

    def is_same_board(self, game: chess.Board) -> bool:
        """main program can check if tutor game is still in sync with same move stacks"""
        return self.board.fen() == game.fen()

    def newgame(self):
        """reset everything - game board becomes starting position
        analyser is stopped"""
        self._reset_to_new_position(chess.Board(), new_game=True)
        self.expl_start_position = True  # make sure opening moves are explored

    def _reset_to_new_position(self, game: chess.Board, new_game: bool = False):
        """update position and delete history - re-sync position
        the engine analyser will be stopped, start it again if needed
        you can indicate that this is a new game
        eval comments to PGN will reset if new_game is True"""
        self.stop()
        if new_game:
            self.evaluated_moves = {}  # forget evals from last game
            self.pgn_game = None  # forget loaded PGN game
            logger.debug("picotutor reset to new position and newgame")
        else:
            logger.debug("picotutor reset to new position")
        self._reset_color_coded_vars()
        self.board = game.copy()
        # opening move explorer vars
        self.op = []
        if self.board.board_fen() == chess.STARTING_BOARD_FEN:
            if not new_game:
                logger.debug("strange - tutor position set to starting without newgame")
            self.expl_start_position = True
        else:
            self.expl_start_position = False

    def _reset_history_vars(self, game: chess.Board):
        """reset and forget history only - needed when history is out of sync
        this is a lighter version of _reset_to_new_position
        it leaves analyser running - caller must check board sync
        if you send a different game board analyser is stopped and board copied"""
        if game.fen() != self.board.fen():
            self.stop()  # only stop analysing if its wrong game
            self.board = game.copy()
        self._reset_color_coded_vars()  # all has to go? analysis starts over?
        self.op = []  # unfortunatly pop is out of sync so we lose this

    def _reset_color_coded_vars(self):
        """reset and forget all color coded variables - needs to be done on new position"""
        # snapshot list of best = deep/max-ply, and obvious = shallow/low-ply
        # lists of InfoDict per color - filled in eval_legal_moves()
        self.best_info = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_info = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # snapshot of best_moves and obvious_moves are filled in _eval_pv_list()
        # information comes from InfoDict snapshot lists above: best_info and obvious_info
        # "almost" complete 5-50 list of tuple(pv_key, move, score, mate)
        self.best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # history list of user move selected from best_moves and obvious_moves above
        # tuple(pv_key, move, score, mate) copy for selected user move
        # pv_key is the index to the snapshot best_info and obvious_info
        # index = None indicates was not found in InfoDict results
        # index not None has no value in history as its an index to a snapshot above
        self.best_history = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_history = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # pv_user_move and pv_best_move are the pv array from InfoDict analysis
        # these could be changed to local variables in eval_user_moves
        self.pv_user_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.pv_best_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.hint_move = {color: chess.Move.null() for color in [chess.WHITE, chess.BLACK]}
        # alt_best_moves are filled in eval_legal_moves()
        self.alt_best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}

    async def set_user_color(self, i_user_color, analyse_both_sides: bool):
        """set the user color to analyse moves for, normally engine is playing the other side
        if you send analyse_both_sides True it means both sides will be analysed"""
        logger.debug("picotutor set user color %s", i_user_color)
        if self.user_color != i_user_color or self.analyse_both_sides != analyse_both_sides:
            # if new user colour and we are not going to analyse both sides
            # one history colour is going to become old and obsolete
            # but pop_user_move will detect it and delete history
            self.user_color = i_user_color
            self.analyse_both_sides = analyse_both_sides
            # no need to reset_color_coded_vars
            await self._start_or_stop_as_needed()

    def get_user_color(self):
        return self.user_color

    async def set_position(self, game: chess.Board, new_game: bool = False):
        """main calls this to re-set position to same as main
        this re-synchronizes the main chess board with tutors own
        it is not a newgame - for newgame call reset or send new_game True"""
        logger.debug("set_position called")
        self._reset_to_new_position(game, new_game)

        if not (self.coach_on or self.watcher_on):
            return
        # at the moment pico main always calls set_user_color after this
        # therefore no self._start_or_stop_as_needed()
        # @ todo: combine set_colour into this call
        # that is why we leave the if not() above for now

    async def push_move(self, i_uci_move: chess.Move, game: chess.Board) -> bool:
        """inform picotutor that a board move was made
        returns False if tutor board is out of sync
        and caller must set_position again"""
        try:
            self.op.append(self.board.san(i_uci_move))  # for opening matching
        except AssertionError as e:
            logger.debug("picotutor board not in sync - move %s not legal on tutor board", e)
            return False
        self.board.push(i_uci_move)  # now boards should be in sync, check!
        if game.fen() != self.board.fen():
            logger.debug("picotutor board not in sync when pushing move %s", i_uci_move.uci())
            return False
        c_filler_str = PicoTutor.printable_move_filler(self.board.ply(), self.board.turn)
        logger.debug("picotutor push move %s%s", c_filler_str, i_uci_move.uci())

        if not (self.coach_on or self.watcher_on):
            return True

        if self.analyse_both_sides or self.board.turn != self.user_color:
            # we are analysing both sides or user just made a move, evaluate move
            try:
                await self.eval_legal_moves(self.board.turn)  # take snapshot of current evaluation
                self.eval_user_move(i_uci_move)  # determine & save evaluation of user move
            except IndexError:
                logger.debug("program internal error - no move pushed before evaluation attempt")
        else:
            # we are not analysing both sides or engine just made a move
            try:
                if self.always_run_tutor:
                    # @todo this is intermediate solution for #49, we evaluate engine moves
                    await self.eval_legal_moves(self.board.turn)  # take snapshot of current evaluation
                    self.eval_user_move(i_uci_move)  # determine & save evaluation of user move
                else:
                    self._eval_engine_move(i_uci_move)  # add "dummy" engine move to history
            except IndexError:
                logger.debug("program internal error - no move pushed before storing engine move")
        await self._start_or_stop_as_needed()  # new common code to start or stop analysers
        # self.log_sync_info()  # normally commented out
        return True

    def _update_internal_history_after_pop(self, poped_move: chess.Move) -> bool:
        """return True if history sync with board is ok after pop"""
        result = True
        # we have already poped move - turn coding need to be reversed
        if self.board.turn == chess.WHITE:
            turn = chess.BLACK
        else:
            turn = chess.WHITE
        try:
            pv_key, move, score, mate = self.best_history[turn][-1]
            if move == poped_move:
                self.best_history[turn].pop()
            else:
                result = False
                logger.debug("picotutor pop best move not in sync - probably due to user color change")
            pv_key, move, score, mate = self.obvious_history[turn][-1]
            if move == poped_move:
                self.obvious_history[turn].pop()
            else:
                result = False
                logger.debug("picotutor pop obvious move not in sync - probably due to user color change")
        except IndexError:
            result = False
            logger.debug("picotutor no move history to pop from, color=%s", self.board.turn)
        return result

    def _update_internal_state_after_pop(self, poped_move: chess.Move) -> bool:
        """return True if history sync with board is ok after pop"""
        try:
            self.op.pop()
        except IndexError:
            pass

        if not (self.coach_on or self.watcher_on):
            return False

        result = self._update_internal_history_after_pop(poped_move=poped_move)
        return result

    async def pop_last_move(self, game: chess.Board) -> bool:
        """inform picotutor that move takeback has been done
        returns False if tutor board is out of sync
        and caller must set_position again"""
        result = True
        if self.board.move_stack:
            if game.fen() != self.board.fen():  # not same before pop = ok
                poped_move = self.board.pop()  # now they should be same
                if self.board.fen() == game.fen():
                    logger.debug("picotutor pop move %s colour=%s", poped_move.uci(), self.board.turn)
                    history_ok = self._update_internal_state_after_pop(poped_move)
                    if not history_ok:
                        # result is still True, boards are in sync, history is not
                        logger.warning("picotutor eval for next move must be done without history")
                        self._reset_history_vars(game)  # same game - no re-sync
                else:
                    result = False
                    logger.debug("picotutor board not in sync after takeback")
                    self._reset_history_vars(game)  # re-sync new game board
            else:
                # result is still True, boards have same fen already before pop
                logger.debug("strange - picotutor board already poped - boards are in sync")
        else:
            logger.debug("picotutor board has no move stack in takeback - doing nothing")
            if game.fen() != self.board.fen():
                result = False  # why ask for pop if move stack is empty in main?
        if result:
            await self._start_or_stop_as_needed()  # boards in sync, keep analysing
        else:
            logger.warning("picotutor board out of sync after takeback move")
        self.log_sync_info()  # debug only
        return result

    def get_stack(self):
        return self.board.move_stack

    def get_move_counter(self):
        return self.board.fullmove_number

    async def start(self):
        """start the engine analyser - or update depth if already running
        start_also_obvious_analyser is used to start the obvious engine
        you can override with False to prevent obvious analysis"""
        # after newgame, setposition, pushmove etc events
        if self.best_engine:
            if self.best_engine.loaded_ok():
                if self.coach_on or self.watcher_on:
                    if self.deep_limit_depth:
                        # override for main program when using coach as analyser
                        # used for analysis when tutor engine is same as playing engine
                        limit = Limit(depth=self.deep_limit_depth)
                    else:
                        limit = Limit(depth=c.DEEP_DEPTH)  # default value
                    multipv = c.VALID_ROOT_MOVES
                    await self.best_engine.start_analysis(self.board, limit=limit, multipv=multipv)
            else:
                logger.error("best engine has terminated in picotutor?")
        await asyncio.sleep(0.05)  # give deep engine analysis head start
        if self.obvious_engine:
            if self.obvious_engine.loaded_ok():
                if self.coach_on or self.watcher_on:
                    limit = Limit(depth=c.LOW_DEPTH)
                    multipv = c.LOW_ROOT_MOVES
                    await self.obvious_engine.start_analysis(self.board, limit=limit, multipv=multipv)
            else:
                logger.error("obvious engine has terminated in picotutor?")

    def stop(self):
        """stop the engine analyser"""
        # during thinking time of opponent tutor should be paused
        # after the user move has been pushed
        if self.best_engine:
            self.best_engine.stop()
        if self.obvious_engine:
            self.obvious_engine.stop()

    async def exit_or_reboot_cleanups(self):
        """close the tutor engines and cleanup"""
        self.stop()  # stop engines if running
        if self.best_engine:
            if self.best_engine.loaded_ok():
                await self.best_engine.quit()
            self.best_engine = None
        if self.obvious_engine:
            if self.obvious_engine.loaded_ok():
                await self.obvious_engine.quit()
            self.obvious_engine = None

    async def _start_or_stop_as_needed(self):
        """start or stop analyser as needed"""
        # common logic for all of tutors functions to start or stop
        # determine if tutor should run and start if it should, pause if not
        if self._should_run_tutor():
            await self.start()  # normal both deep and obvious analysis
        elif self.always_run_tutor:
            # @todo intermediate solution #49 forcing deep tutor to run anyway
            await self.start()
        else:
            self.stop()

    def _should_run_tutor(self) -> bool:
        """return True if tutor should run"""
        if not (self.coach_on or self.watcher_on):
            return False  # user has turned tutor off
        # run tutor if we are analysing both sides, or if it is user turn
        return self.analyse_both_sides or self.board.turn == self.user_color

    def log_sync_info(self):
        """logging help to check if picotutor and main picochess are in sync"""
        logger.debug("picotutor op moves %s", self.op)
        moves = self.board.move_stack
        uci_moves = []
        for move in moves:
            uci_moves.append(move.uci())
        logger.debug("picotutor board moves %s", uci_moves)
        for turn in (chess.BLACK, chess.WHITE):
            hist_moves = []
            if self.best_history[turn]:
                for pv_key, move, score, mate in self.best_history[turn]:
                    hist_moves.append(move.uci())
            logger.debug("picotutor history moves %s", hist_moves)
        self.log_eval_moves()

    def log_pv_lists(self, long_version: bool = False):
        """logging help for picotutor developers"""
        if self.board.turn == chess.WHITE:
            logger.debug("PicoTutor White to move")
        else:
            logger.debug("PicoTutor Black to move")
        if self.best_info[self.board.turn]:
            logger.debug("%d best:", len(self.best_info[self.board.turn]))
            for info in self.best_info[self.board.turn]:
                if "pv" in info and "score" in info and "depth" in info:
                    # score_turn must be as BEFORE the move - so opposite
                    score_turn = chess.WHITE if self.board.turn == chess.BLACK else chess.BLACK
                    move, score, mate = PicoTutor.get_score(info, score_turn)
                    logger.debug("%s score %d mate in %d depth %d", move.uci(), score, mate, info["depth"])
                if not long_version:
                    break
        if self.obvious_info[self.board.turn]:
            logger.debug("%d obvious:", len(self.obvious_info[self.board.turn]))
            for info in self.obvious_info[self.board.turn]:
                if "pv" in info and "score" in info and "depth" in info:
                    # score_turn must be as BEFORE the move - so opposite
                    score_turn = chess.WHITE if self.board.turn == chess.BLACK else chess.BLACK
                    move, score, mate = PicoTutor.get_score(info, score_turn)
                    logger.debug("%s score %d mate in %d depth %d", move.uci(), score, mate, info["depth"])
                if not long_version:
                    break

    def _eval_engine_move(self, eng_move: chess.Move):
        """add engine played move to history"""
        # @todo we could take in engine score here and set pv_key = 0
        # same as when user move not found in best move list in eval_user_move
        pv_key = None  # so that we know its not found and score is wrong
        score = mate = 0
        # t tuple(pv_key, move, score, mate)
        t = (pv_key, eng_move, score, mate)
        # when a move is poped, its poped from best and obvious
        self.best_history[self.board.turn].append(t)
        self.obvious_history[self.board.turn].append(t)
        # not sure following is needed but follow same logic as eval_user_move
        self.pv_user_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.pv_best_move = {color: [] for color in [chess.WHITE, chess.BLACK]}

    def eval_user_move(self, user_move: chess.Move):
        """add user move to self.best_history and self.obvious_history
        update self.pv_user_move and self.pv_best_move
        throws IndexError if self.best_info and self.obvious_info is not prepared"""
        if not (self.coach_on or self.watcher_on):
            return
        # t tuple(pv_key, move, score, mate)
        t = self.in_best_moves(user_move)
        # add score to history list
        if t:
            pv_key = t[0]
            self.best_history[self.board.turn].append(t)
            self.pv_best_move = self.best_info[self.board.turn][0]["pv"]
            self.pv_user_move[self.board.turn] = self.best_info[self.board.turn][pv_key]["pv"]
        else:
            logger.debug("did not find user move %s in best moves", user_move.uci())
            pv_key = None  # so that we know its not found
            score = mate = 0
            if self.best_moves[self.board.turn]:
                # user move is <= lowest score seen, last on list
                pv_extra_key, extra_move, score, mate = self.best_moves[self.board.turn][-1]
            self.best_history[self.board.turn].append((pv_key, user_move, score, mate))
            self.pv_user_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
            self.pv_best_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        t = self.in_obvious_moves(user_move)
        # add score to history list
        if t:
            # pv_key = t[0]
            self.obvious_history[self.board.turn].append(t)
        else:
            logger.debug("did not find user move %s in obvious moves", user_move.uci())
            pv_key = None  # so that we know its not found
            score = mate = 0
            if self.obvious_moves[self.board.turn]:
                # user move is <= lowest score seen, last on list
                pv_extra_key, extra_move, score, mate = self.obvious_moves[self.board.turn][-1]
            self.obvious_history[self.board.turn].append((pv_key, user_move, score, mate))

    def in_best_moves(self, user_move: chess.Move) -> tuple:
        """find move in obvious moves
        return None or tuple(pv_key, move, score, mate)"""
        for t in self.best_moves[self.board.turn]:
            # tuple index 1 is move
            if t[1] == user_move:
                return t
        return None

    def in_obvious_moves(self, user_move: chess.Move) -> tuple:
        """find move in obvious moves
        return None or tuple(pv_key, move, score)"""
        for t in self.obvious_moves[self.board.turn]:
            # tuple index 1 is move
            if t[1] == user_move:
                return t
        return None

    def sort_score(self, tupel):
        """define score:int as sort key"""
        return tupel[2]

    @staticmethod
    def get_score(info: InfoDict, turn: chess.Color = chess.WHITE) -> tuple:
        """return tuple (move, score, mate) extracted from info
        if no turn is given, it defaults to white
        if no score is found, score is None"""
        if "pv" in info:
            move = info["pv"][0] if info["pv"] else chess.Move.null()
        else:
            move = chess.Move.null()
        score = None
        mate = 0
        if "score" in info:
            score_val = info["score"]
            m = score_val.pov(turn).mate()
            mate = 0 if m is None else m
            if score_val.is_mate():
                score = score_val.pov(turn).score(mate_score=99999)
            else:
                score = score_val.pov(turn).score()
        else:
            logger.debug("no score in tutor info dict")
        return (move, score, mate)

    # @todo re-design this method?
    @staticmethod
    def _eval_pv_list(turn: chess.Color, info_list: list[InfoDict], moves) -> int | None:
        """fill in best_moves or obvious_moves (param moves) from InfoDict list
        it assumes best_moves is emptied before called
        :return the best score"""
        best_score = -99999
        pv_key = 0  # index in InfoDict list
        while pv_key < len(info_list):
            info: InfoDict = info_list[pv_key]
            # score_turn must be as BEFORE the move - so opposite
            # because turn is after the move being scored
            score_turn = chess.WHITE if turn == chess.BLACK else chess.BLACK
            move, score, mate = PicoTutor.get_score(info, score_turn)
            if move != chess.Move.null():
                moves.append((pv_key, move, score, mate))
                # put an score: int here for sorting best moves
                if score is not None:
                    best_score = max(best_score, score)
            pv_key = pv_key + 1
        return best_score

    async def eval_legal_moves(self, turn: chess.Color, analysed_move_already_done: bool = True):
        """Update analysis information from engine analysis snapshot
        parameter analysed_move_already_done is True if self.board already has a move
        for the side to be analysed"""
        # @todo check if this can throw exceptions
        if not (self.coach_on or self.watcher_on):
            return
        self.best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.alt_best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # eval_pv_list below will build new lists
        board_before_usermove: chess.Board = self.board.copy()
        if analysed_move_already_done:
            # this is the normal situation, the move to be analysed done on board
            # board fen will not match analysis board unless we pop it
            try:
                #  for some strange reason the following line shows E1101
                board_before_usermove.pop()  # we ask for analysis done before user move
            except IndexError:
                logger.debug("can not evaluate empty board 1st move")
                return
        # else situation is for get_pos_analysis() where no move is done yet
        obvious_result = await self.obvious_engine.get_analysis(board_before_usermove)
        self.obvious_info[turn] = obvious_result.get("info")
        best_result = await self.best_engine.get_analysis(board_before_usermove)
        self.best_info[turn] = best_result.get("info")
        if self.best_info[turn]:
            best_score = PicoTutor._eval_pv_list(turn, self.best_info[turn], self.best_moves[turn])
            if self.best_moves[turn]:
                self.best_moves[turn].sort(key=self.sort_score, reverse=True)
                # collect possible good alternative moves
                for pv_key, move, score, mate in self.best_moves[turn]:
                    if move:
                        diff = abs(best_score - score)
                        if diff <= c.ALTERNATIVE_TH:
                            self.alt_best_moves[turn].append(move)
        if self.obvious_info[turn]:
            PicoTutor._eval_pv_list(turn, self.obvious_info[turn], self.obvious_moves[turn])
            if self.obvious_moves[turn]:
                self.obvious_moves[turn].sort(key=self.sort_score, reverse=True)
        self.log_pv_lists()  # debug only

    async def get_analysis(self) -> dict:
        """get analysis info from engine - returns dict with info and fen
        the info element is a list of InfoDict
        the fen element is board position that was analysed"""
        # failed answer is empty lists
        result = {"info": [], "fen": ""}
        if self.best_engine:
            if self.best_engine.is_analyser_running():
                result = await self.best_engine.get_analysis(self.board)
        return result

    def get_user_move_eval(self) -> tuple:
        """for main program to get the evaluation of the previous move
        return (str int) which is (eval sts, moves to mate"""
        eval_string = ""
        best_mate = 0
        best_score = 0
        best_move = chess.Move.null()
        if not (self.coach_on or self.watcher_on):
            return eval_string, 0

        # all history list have tuples: (pv,move,score,mate)
        # where pv can be None if score and mate are not available
        # move is always valid, even for fake history tuples

        # best and obvious history tuples needed, and min 2 moves analysed
        if (
            len(self.best_history[self.board.turn]) < 1
            or len(self.obvious_history[self.board.turn]) < 1
            or len(self.best_moves[self.board.turn]) < 2
        ):
            return eval_string, 0

        #  best score/move is the first in the list - needed to proceed
        best_pv, best_move, best_score, best_mate = self.best_moves[self.board.turn][0]
        if best_pv is None:
            logger.debug("cannot evaluate move as best move data is missing")
            return eval_string, 0

        # best/deep/max-ply engine analysis
        current_pv, current_move, current_score, current_mate = self.best_history[self.board.turn][-1]

        # obvious/shallow/min-ply engine analysis
        low_pv, low_move, low_score, low_mate = self.obvious_history[self.board.turn][-1]

        # dig into best/deep/max-ply history for before_score for previous user move
        if len(self.best_history[self.board.turn]) > 1:
            before_pv, before_move, before_score, before_mate = self.best_history[self.board.turn][-2]
            if before_pv is None:  # pv_key index - move not analysed
                before_score = None  # history not usable, fake-move or missed
        else:
            before_score = None

        # optimisations in Picochess 4 - 200 wide multipv searches reduced to to 50 ish
        # approximation_in_use is True when user misses either obvious or best history
        # user move might be missing in obvious history - can happen!
        #  --> low_score is lowest seen score, known by low_pv is None
        # user move might also be missing in best history
        #  --> current_score is lowest seen score, known by current_pv is None
        logger.debug("Score: %d", current_score)
        best_deep_diff = best_score - current_score
        deep_low_diff = current_score - low_score
        approximations_in_use = current_pv is None or low_pv is None
        c_move_str = PicoTutor.printable_move_filler(self.board.ply(), self.board.turn)
        c_move_str += current_move.uci()
        if approximations_in_use:
            logger.debug("approximations in use - only evaluating ? and ??")
            logger.debug("current_pv=%s low_pv=%s", current_pv, low_pv)
            logger.debug("approximated minimum CPL: %d for move %s", best_deep_diff, c_move_str)
        else:
            logger.debug("CPL: %d for move %s", best_deep_diff, c_move_str)
            logger.debug("deep_low_diff = %d", deep_low_diff)
        if before_score is not None:
            score_hist_diff = current_score - before_score
            history_in_use = True
            logger.debug("score_hist_diff = %d", score_hist_diff)
        else:
            score_hist_diff = 0  # missing history before score
            history_in_use = False
            logger.debug("history before move not available - not evaluating !? and ?!")

        # count legal moves in current position (for this we have to undo the user move)
        try:
            board_before_usermove: chess.Board = self.board.copy()
            board_before_usermove.pop()
            legal_no = board_before_usermove.legal_moves.count()
            logger.debug("number of legal moves %d", legal_no)
        except IndexError:
            # board_before_usermove.pop() failed, legal_no = 0
            legal_no = 0
            logger.debug("program internal error - no move pushed before evaluation attempt")
        if legal_no < 2:
            # there is no point evaluating the only legal or no pop()?
            eval_string = ""
            return eval_string, 0

        ###############################################################
        # 1. bad moves
        ##############################################################
        eval_string = ""

        # Blunder ??
        if best_deep_diff > c.VERY_BAD_MOVE_TH:
            eval_string = "??"

        # Mistake ?
        elif best_deep_diff > c.BAD_MOVE_TH:
            eval_string = "?"

        # Dubious
        # Dont score if approximations in use
        elif (
            not approximations_in_use
            and history_in_use
            and best_deep_diff > c.DUBIOUS_TH
            and (abs(deep_low_diff) > c.UNCLEAR_DIFF)
            and (score_hist_diff > c.POS_INCREASE)
        ):
            eval_string = "?!"

        ###############################################################
        # 2. good moves
        ##############################################################
        eval_string2 = ""

        if not approximations_in_use:
            # very good moves
            if best_deep_diff <= c.VERY_GOOD_MOVE_TH and (deep_low_diff > c.VERY_GOOD_IMPROVE_TH):
                if (best_score == 99999 and (best_mate == current_mate)) and legal_no <= 2:
                    pass
                else:
                    eval_string2 = "!!"

            # good move
            elif best_deep_diff <= c.GOOD_MOVE_TH and (deep_low_diff > c.GOOD_IMPROVE_TH) and legal_no > 1:
                eval_string2 = "!"

            # interesting move
            elif (
                history_in_use
                and best_deep_diff < c.INTERESTING_TH
                and (abs(deep_low_diff) > c.UNCLEAR_DIFF)
                and (score_hist_diff < c.POS_DECREASE)
            ):
                eval_string2 = "!?"

        if eval_string2 != "":
            if eval_string == "":
                eval_string = eval_string2

        # remember this evaluation for later pgn generation in PgnDisplay
        # key to find evaluation later =(ply halfmove number: int, move: chess.Move)
        # not always unique if we have takeback sequence with other moves
        # should work since we evaluate all moves and remove if no evaluation
        e_key = (self.board.ply(), current_move, self.board.turn)  # ply, turn is AFTER current_move
        e_value = {}  # collect eval values for the move here
        e_value["nag"] = PicoTutor.symbol_to_nag(eval_string)
        try:
            # board_before_usermove is where we have popped the user move above
            e_value["best_move"] = board_before_usermove.san(best_move)
            e_value["user_move"] = board_before_usermove.san(current_move)
            logger.debug("best move: %s, user move: %s", e_value["best_move"], e_value["user_move"])
        except (KeyError, ValueError, AttributeError):
            logger.warning("picotutor failed to convert to san for %s", current_move)
        if e_value["nag"] == chess.pgn.NAG_NULL:
            # no NAG to store, due to takeback make sure this e_key eval is empty
            self.evaluated_moves.pop(e_key, None)  # None prevents KeyError
            # special case, if inaccurate move store DS, also when approximated
            if best_deep_diff > c.INACCURACY_TH:
                e_value["CPL"] = best_deep_diff  # lost centipawns
                if current_pv is not None:
                    e_value["score"] = current_score
                self.evaluated_moves[e_key] = e_value  # ok with current_pv None (approx)
        elif current_pv is not None:
            # user move identified, not approximated, ok to log to PGN file
            e_value["CPL"] = best_deep_diff  # lost centipawns
            if current_mate != 0:
                e_value["mate"] = current_mate
            e_value["score"] = current_score  # eval score
            if low_pv is not None:  # low also identified, needs both current_pv AND low
                e_value["deep_low_diff"] = deep_low_diff  # Cambridge delta S
            if before_score is not None:  # not approximated, need both current_pv AND history
                e_value["score_hist_diff"] = score_hist_diff
            self.evaluated_moves[e_key] = e_value

        self.log_sync_info()  # debug only

        # information return in addition:
        # threat move / bestmove/ pv line of user and best pv line so picochess can comment on that as well
        # or call a pico talker method with that information
        self.hint_move[self.board.turn] = best_move

        logger.debug("evaluation %s", eval_string)
        return eval_string, current_mate

    @staticmethod
    def symbol_to_nag(eval_string: str) -> int:
        """convert an evaluation string like ! to NAG format like NAG_GOOD_MOVE"""
        symbol_to_nag = {
            "!": chess.pgn.NAG_GOOD_MOVE,  # $1
            "?": chess.pgn.NAG_MISTAKE,  # $2
            "!!": chess.pgn.NAG_BRILLIANT_MOVE,  # $3
            "??": chess.pgn.NAG_BLUNDER,  # $4
            "!?": chess.pgn.NAG_SPECULATIVE_MOVE,  # $5
            "?!": chess.pgn.NAG_DUBIOUS_MOVE,  # $6
        }
        # empty or unrecognized str becomes NAG_NULL
        return symbol_to_nag.get(eval_string, chess.pgn.NAG_NULL)

    @staticmethod
    def nag_to_symbol(nag: int) -> str:
        """convert NAG format like NAG_GOOD_MOVE to an evaluation string like !"""
        nag_to_symbol = {
            chess.pgn.NAG_GOOD_MOVE: "!",
            chess.pgn.NAG_MISTAKE: "?",
            chess.pgn.NAG_BRILLIANT_MOVE: "!!",
            chess.pgn.NAG_BLUNDER: "??",
            chess.pgn.NAG_SPECULATIVE_MOVE: "!?",
            chess.pgn.NAG_DUBIOUS_MOVE: "?!",
            chess.pgn.NAG_NULL: "",
        }
        # NAG_NULL or unrecognized NAG becomes empty str
        return nag_to_symbol.get(nag, "")

    # Logic on halfmoves and fullmoves and move identification is
    # that we consider things AFTER the move has been done
    # fullmove, halfmove (ply), turn, all AFTER...
    # Example: After Bb5 we have 5 halfs, and 2 full, Black turn
    # Halfmove | Turn   | Fullmove | SAN
    # -------- | ------ | -------- | -----
    #    0     | White  |    0     | —
    #    1     | Black  |    0     | e4
    #    2     | White  |    1     | e5
    #    3     | Black  |    1     | Nf3
    #    4     | White  |    2     | Nc6
    #    5     | Black  |    2     | Bb5
    #    6     | White  |    3     | a6
    #    7     | Black  |    3     | Ba4
    #
    # SPECIAL: Black starts from a position setup, for example
    # assume 1.e4 was done but we dont know the move, just the position
    # Halfmove | Turn   | Fullmove | SAN
    # -------- | ------ | -------- | -----
    #    0     | Black  |    0     | e5
    #    1     | White  |    1     | Nf3
    #    2     | Black  |    1     | Nc6
    #    3     | White  |    2     | Bb5
    #    4     | Black  |    2     | a6
    #    5     | White  |    3     | Ba4
    #    6     | Black  |    3     | Nf6
    #    7     | White  |    4     | —

    # Note that board.fullmove_number does NOT decrease after board.pop()
    # but ply() is correct, so always take ply() first then convert to fullmove_number
    @staticmethod
    def halvmove_to_simple_fullmove(halfmove_nr: int, turn: chess.Color) -> int:
        """simplified method when you know turn and
        dont care if it was first_move_black"""
        t = PicoTutor.halfmove_to_fullmove(halfmove_nr, turn)
        return t[0]  # see tuple returned from method below

    @staticmethod
    def halfmove_to_fullmove(halfmove_nr: int, known_turn: chess.Color = None) -> Tuple:
        """convert halfmove_nr after a move to a fullmove_nr and turn
        1. e4 = halfmove 1 = fullmove 0, 1.-e5 = halfmove 2 = fullmove 1
        To support setup position with a black first move we need known_turn
        if known_turn not given its assumed that White made the first move
        and in this case the first_move_black will always return False"""
        assert halfmove_nr >= 0
        ply = halfmove_nr
        # BLACK has even halfnumbers = next turn is WHITE (see table above)
        turn = chess.WHITE if halfmove_nr % 2 == 0 else chess.BLACK
        if known_turn is not None and known_turn != turn:
            ply = ply + 1  # add missing whites first move before converting
            turn = known_turn  # return known turn as it differs
            first_move_black = True  # inform caller that Black move first
        else:
            first_move_black = False  # normal situation with White move first
        fullmove_nr = ply // 2  # simplest, see table above
        return fullmove_nr, turn, first_move_black

    @staticmethod
    def printable_fullmove(halfmove_nr: int, turn: chess.Color) -> int:
        """return fullmove to use when printing moves
        1. e4 = = fullmove 0 --> 1, 1.-e5 = fullmove 1 --> 1"""
        assert halfmove_nr >= 0
        fullmove_nr = PicoTutor.halvmove_to_simple_fullmove(halfmove_nr, turn)
        # for fullmove 0 and turn WHITE return value will be zero = unprintable
        return fullmove_nr + 1 if turn == chess.BLACK else fullmove_nr

    @staticmethod
    def printable_move_filler(halfmove_nr: int, turn: chess.Color) -> str:
        """return filler str to put in front of uci or san move str
        notice that input is halfmove_nr you get using board.ply()"""
        filler_str = str(PicoTutor.printable_fullmove(halfmove_nr, turn))
        filler_str += ". - " if turn == chess.WHITE else ". "
        return filler_str

    @staticmethod
    def fullmove_to_halfmove(fullmove_nr: int, turn: chess.Color, first_move_black: bool = None) -> int:
        """convert back from fullmove to halfmove after a move
        1. e4 = halfmove 1 = fullmove 0, 1.-e5 = halfmove 2 = fullmove 1
        Note that board.pop() does not reduce fullmove number
        To support setup position with black first move we need to know first_move_black
        By default its assumed that White made the first move unless first_move_black=True"""
        assert fullmove_nr >= 0
        # for fullmove 0 and turn WHITE return value will be 0 = no move done
        # for fullmove 0 and turn BLACK White has moved once, or position setup
        halfmove_nr = fullmove_nr * 2
        if turn == chess.BLACK:
            halfmove_nr = halfmove_nr + 1  # add one halfmove after WHITE move
        if first_move_black is not None and first_move_black is True and halfmove_nr > 0:
            halfmove_nr = halfmove_nr - 1  # reduce with missing first WHITE move
        return halfmove_nr

    def get_eval_moves(self) -> dict:
        """return a dict of all evaluated moves"""
        return self.evaluated_moves

    def log_eval_moves(self):
        """debugging help to check list of evaluated moves"""
        logger.debug("picotutor evaluated moves:")
        for (halfmove_nr, user_move, known_turn), value in self.evaluated_moves.items():
            try:
                # example 2. d4! (fullmove 1) or 2. - exd4! (fullmove 2)
                # example 2. d4! (halfmove 3) or 2. - exd4! (halfmove 4)
                move_str = PicoTutor.printable_move_filler(halfmove_nr, known_turn)
                move_str += value.get("user_move", "")  # pre-stored short san for user_move
                best_move_str = value.get("best_move", "")
                nag_str = PicoTutor.nag_to_symbol(value.get("nag"))
                eval_score = " Score: " + str(value.get("score")) if "score" in value else ""
                lcp_str = " CPL: " + str(value.get("CPL")) if "CPL" in value else ""
                diff_str = " DS: " + str(value.get("deep_low_diff")) if "deep_low_diff" in value else ""
                hist_str = " hist: " + str(value.get("score_hist_diff")) if "score_hist_diff" in value else ""
                logger.debug(
                    "%s%s {best was %s%s%s%s%s}",
                    move_str,
                    nag_str,
                    best_move_str,
                    eval_score,
                    lcp_str,
                    diff_str,
                    hist_str,
                )
            except (KeyError, ValueError, AttributeError):
                logger.debug("failed to log full list of evaluated moves in picotutor")
                # dont care, just dont let this debug crash picotutor

    def get_user_move_info(self) -> tuple:
        """return a tuple of (hint move, pv) if tutor is on, where
        - pv is the analysed InfoDict pv array of user chosen move
        if tutor is deactivated by user it returns (chess.Move.null(), [])"""
        if not (self.coach_on or self.watcher_on):
            return chess.Move.null(), []  # no move, no pv list
        # not sending self.pv_best_move as its not used?
        return self.hint_move[self.board.turn], self.pv_user_move[self.board.turn]

    async def get_pos_analysis(self):
        if not (self.coach_on or self.watcher_on):
            return
        # calculate material / position / mobility / development / threats / best move / best score
        # call a picotalker method with these information
        mate = 0
        score = 0
        # self.log_sync_info()  # normally commented out

        # in this get_pos_analysis there is no user move to pop, send opposite turn and False
        turn: chess.Color = chess.WHITE if self.board.turn == chess.BLACK else chess.BLACK
        await self.eval_legal_moves(turn, False)  # take snapshot of analysis before user move
        info: InfoDict = self.best_info[turn][0] if self.best_info[turn] else None
        if not info:
            logger.debug("no best info in get_pos_analysis for turn %s", turn)
            return
        (best_move, score, mate) = PicoTutor.get_score(info)
        # main pitotutor expects pawns, not centipawns
        if score is not None:
            score = score / 100.0
        return best_move, score, mate, self.alt_best_moves[turn]
