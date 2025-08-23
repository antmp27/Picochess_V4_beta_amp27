# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#                         Johan Sjöblom (messier109@gmail.com)
#
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

import asyncio
from asyncio import CancelledError
import os
from typing import Optional, Iterable
import logging
import configparser
import copy

import spur  # type: ignore
import paramiko

import chess.engine  # type: ignore
from chess.engine import InfoDict, Limit, UciProtocol, AnalysisResult, PlayResult
from chess import Board  # type: ignore
from uci.rating import Rating, Result
from utilities import write_picochess_ini

FLOAT_MAX_ENGINE_TIME = 1.0  # engine fallback thinking time
FLOAT_ANALYSIS_WAIT = 0.1  # save CPU in ContinuousAnalysis

UCI_ELO = "UCI_Elo"
UCI_ELO_NON_STANDARD = "UCI Elo"
UCI_ELO_NON_STANDARD2 = "UCI_Limit"

logger = logging.getLogger(__name__)


class WindowsShellType:
    """Shell type supporting Windows for spur."""

    supports_which = True

    def generate_run_command(self, command_args, store_pid, cwd=None, update_env=None, new_process_group=False):
        if not update_env:
            update_env = {}
        if new_process_group:
            raise spur.ssh.UnsupportedArgumentError("'new_process_group' is not supported when using a windows shell")

        commands = []
        if command_args[0] == "kill":
            command_args = self.generate_kill_command(command_args[-1]).split()

        if store_pid:
            commands.append("powershell (Get-WmiObject Win32_Process -Filter ProcessId=$PID).ParentProcessId")

        if cwd is not None:
            commands.append(
                "cd {0} 2>&1 || ( echo. & echo spur-cd: %errorlevel% & exit 1 )".format(self.win_escape_sh(cwd))
            )
            commands.append("echo. & echo spur-cd: 0")

        update_env_commands = ["SET {0}={1}".format(key, value) for key, value in update_env.items()]
        commands += update_env_commands
        commands.append(
            "( (powershell Get-Command {0} > nul 2>&1) && echo 0) || (echo %errorlevel% & exit 1)".format(
                self.win_escape_sh(command_args[0])
            )
        )

        commands.append(" ".join(command_args))
        return " & ".join(commands)

    def generate_kill_command(self, pid):
        return "taskkill /F /PID {0}".format(pid)

    @staticmethod
    def win_escape_sh(value):
        return '"' + value + '"'


class UciShell(object):
    """Handle the uci engine shell."""

    def __init__(self, hostname=None, username=None, key_file=None, password=None, windows=False):
        super(UciShell, self).__init__()
        if hostname:
            logger.info("connecting to [%s]", hostname)
            shell_params = {
                "hostname": hostname,
                "username": username,
                "missing_host_key": paramiko.AutoAddPolicy(),
            }
            if key_file:
                shell_params["private_key_file"] = key_file
            else:
                shell_params["password"] = password
            if windows:
                shell_params["shell_type"] = WindowsShellType()

            self._shell = spur.SshShell(**shell_params)
        else:
            self._shell = None

    def __getattr__(self, attr):
        """Dispatch unknown attributes to SshShell."""
        return getattr(self._shell, attr)

    def get(self):
        return self if self._shell is not None else None


class ContinuousAnalysis:
    """class for continous analysis from a chess engine"""

    def __init__(self, engine: UciProtocol, delay: float, loop: asyncio.AbstractEventLoop, engine_debug_name: str):
        """
        A continuous analysis generator that runs as a background async task.

        :param delay: Time interval to do CPU saving sleep between analysis.
        """
        self.game = None  # latest position requested to be analysed
        self.limit_reached = False  # True when limit reached for position
        self.current_game = None  # latest position being analysed
        self.delay = delay
        self._running = False
        self._task = None
        self._analysis_data = None  # InfoDict list
        self.loop = loop  # main loop everywhere
        self.whoami = engine_debug_name  # picotutor or engine
        self.limit = None  # limit for analysis - set in start
        self.multipv = None  # multipv for analysis - set in start
        self.lock = asyncio.Lock()
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Start unpaused
        self.engine: UciProtocol = engine
        self._idle = True  # start with Engine marked as idle
        self.game_id = 1  # signal ucinewgame to engine when this game id changes
        self.current_game_id = 1  # latest game_id being analysed
        if not self.engine:
            logger.error("%s ContinuousAnalysis initialised without engine", self.whoami)

    def newgame(self):
        """start a new game - it only updates the game parameter in Play calls"""
        self.game_id = self.game_id + 1

    async def _engine_move_task(
        self,
        game: Board,
        limit: Limit,
        ponder: bool,
        result_queue: asyncio.Queue,
        root_moves: Optional[Iterable[chess.Move]],
    ) -> None:
        """async task to ask the engine for a move - to avoid blocking result is put in queue"""
        try:
            self._idle = False  # engine is going to be busy now
            r_info = chess.engine.INFO_SCORE | chess.engine.INFO_PV | chess.engine.INFO_BASIC
            result = await self.engine.play(
                board=copy.deepcopy(game),
                limit=limit,
                game=self.game_id,
                info=r_info,
                ponder=ponder,
                root_moves=root_moves,
            )
            await result_queue.put(result)
            self._idle = True  # engine idle again
        except chess.engine.EngineError:
            await result_queue.put(None)
            self._idle = True  # engine idle again

    def is_idle(self) -> bool:
        """return True if engine is not thinking about a move"""
        return self._idle

    async def play_move(
        self,
        game: Board,
        limit: Limit,
        ponder: bool,
        result_queue: asyncio.Queue,
        root_moves: Optional[Iterable[chess.Move]],
    ) -> None:
        """Plays the best move and return played move result in the queue"""
        self.pause_event.clear()  # Pause analysis to prevent chess library from crashing
        try:
            async with self.lock:
                self.loop.create_task(
                    self._engine_move_task(
                        copy.deepcopy(game),
                        limit=limit,
                        ponder=ponder,
                        result_queue=result_queue,
                        root_moves=root_moves,
                    )
                )
                # @todo we could update the current game here
                # so that analysis on user turn would start immediately
        except chess.engine.EngineTerminatedError:
            logger.error("Engine terminated while trying to make a move")  # @todo find out, why this can happen!
            await result_queue.put(None)  # no result
        finally:
            self.pause_event.set()  # Resume analysis

    def is_limit_reached(self) -> bool:
        """return True if limit was reached for position being analysed"""
        return self.limit_reached

    async def _watching_analyse(self):
        """Internal function for continuous analysis in the background."""
        debug_once_limit = True
        debug_once_game = True
        self.limit_reached = False  # True when depth limit reached for position
        while self._running:
            try:
                if not self._game_analysable(self.game):
                    if debug_once_game:
                        logger.debug("%s ContinuousAnalyser no game to analyse", self.whoami)
                        debug_once_game = False  # dont flood log
                    await asyncio.sleep(self.delay * 2)
                    continue
                # important to check limit AND that game is still same - bug fix 13.4.2025
                if self.limit_reached and self.current_game_id == self.game_id and self.get_fen() == self.game.fen():
                    if debug_once_limit:
                        logger.debug("%s ContinuousAnalyser analysis limited", self.whoami)
                        debug_once_limit = False  # dont flood log
                    await asyncio.sleep(self.delay * 2)
                    continue
                async with self.lock:
                    # new limit, position, possibly new game_id infinite analysis
                    self.current_game = self.game.copy()  # position
                    self.limit_reached = False
                    self.current_game_id = self.game_id  # new id for each game
                    self._analysis_data = None
                debug_once_limit = True  # ok to debug once more after coming here again
                debug_once_game = True
                await self._analyse_forever(self.limit, self.multipv)
            except asyncio.CancelledError:
                logger.debug("%s ContinuousAnalyser cancelled", self.whoami)
                # same situation as in stop
                self._task = None
                self._running = False
            except chess.engine.EngineTerminatedError:
                logger.debug("Engine terminated while analysing - maybe user switched engine")
                # have to stop analysing
                self._task = None
                self._running = False
            except chess.engine.AnalysisComplete:
                logger.debug("ContinuousAnalyser ran out of information")
                asyncio.sleep(self.delay * 2)  # maybe it helps to wait some extra?

    async def _analyse_forever(self, limit: Limit | None, multipv: int | None) -> None:
        """analyse forever if no limit sent"""
        with await self.engine.analysis(
            board=self.current_game, limit=limit, multipv=multipv, game=self.game_id
        ) as analysis:
            async for info in analysis:
                await self.pause_event.wait()  # Wait if analysis is paused
                async with self.lock:
                    # after waiting, check if analysis to be stopped
                    if (
                        not self._running
                        or self.current_game_id != self.game_id
                        or self.current_game.fen() != self.game.fen()
                    ):
                        self._analysis_data = None  # drop ref into library
                        try:
                            analysis.stop()  # ask engine to stop analysing
                        except Exception:
                            logger.debug("failed sending stop in infinite analysis")
                        return  # quit analysis
                    updated = self._update_analysis_data(analysis)  # update to latest
                    if updated:
                        #  self._analysis data got a value
                        #  self.debug_analyser()  # normally commented out
                        if limit:
                            # @todo change 0 to -1 to get all multipv finished
                            info_limit: InfoDict = self._analysis_data[0]
                            if "depth" in info_limit and limit.depth:
                                if info_limit.get("depth") >= limit.depth:
                                    self.limit_reached = True
                                    return  # limit reached
                await asyncio.sleep(self.delay)  # save cpu
                # else just wait for info so that we get updated True

    def debug_analyser(self):
        """use this debug call to see how low and deep depth evolves"""
        # lock is on when we come here
        if self._analysis_data:
            j: InfoDict = self._analysis_data[0]
            if "depth" in j:
                logger.debug("%s ContinuousAnalyser deep depth: %d", self.whoami, j.get("depth"))

    def _update_analysis_data(self, analysis: AnalysisResult) -> bool:
        """internal function for updating while analysing
        returns True if data was updated"""
        # lock is on when we come here
        result = False
        if analysis.multipv:
            self._analysis_data = analysis.multipv
            result = True
        return result

    def _game_analysable(self, game: chess.Board) -> bool:
        """return True if game is analysable"""
        if game is None:
            return False
        if game.is_game_over():
            return False
        if game.fen() == chess.Board.starting_fen:
            return False  # dont waste CPU on analysing starting position
        return True

    def start(self, game: chess.Board, limit: Limit | None = None, multipv: int | None = None):
        """Starts the analysis.

        :param game: The current position to analyse.
        :param limit: limit the analysis, None means forever
        :param multipv: analyse with multipv, None means 1
        """
        if not self._running:
            if not self.engine:
                logger.error("%s ContinuousAnalysis cannot start without engine", self.whoami)
            else:
                self.game = game.copy()  # remember this game position
                self.limit_reached = False  # True when limit reached for position
                self.limit = limit
                self.multipv = multipv
                self._running = True
                self._task = self.loop.create_task(self._watching_analyse())
                logging.debug("%s ContinuousAnalysis started", self.whoami)
        else:
            logging.info("%s ContinuousAnalysis already running - strange!", self.whoami)

    def get_limit_depth(self) -> int | None:
        """return the limit.depth used by analysis - None if no limit or no limit.depth"""
        if self.limit:
            return self.limit.depth
        return None

    def update_limit(self, limit: Limit | None):
        """update the limit for the analysis - first check if needed"""
        if self._running:
            self.limit = limit  # None is also OK here
        else:
            logger.debug("%s ContinuousAnalysis not running - cannot update", self.whoami)

    def stop(self):
        """Stops the continuous analysis - in a nice way
        it lets infinite analyser stop by itself"""
        if self._running:
            self._running = False  # causes infinite analysis loop to send stop to engine
            logging.debug("%s asking for ContinuousAnalysis to stop running", self.whoami)

    def cancel(self):
        """force the analyser to stop by cancelling the async task"""
        if self._running:
            if self._task is not None:
                logger.debug("%s Cancelling ContinuousAnalysis by killing task", self.whoami)
                self._task.cancel()
                self._task = None
                self._running = False
            else:
                logger.debug("ContinousAnalyser strange - running but task is none")

    def get_fen(self) -> str:
        """return the fen the analysis is based on"""
        return self.current_game.fen() if self.current_game else ""

    async def get_analysis(self) -> dict:
        """:return: deepcopied first low and latest best lists of InfoDict
        key 'low': first low limited shallow list of InfoDict (multipv)
        key 'best': a deep list of InfoDict (multipv)
        """
        # due to the nature of the async analysis update it
        # continues to update it all the time, deepcopy needed
        async with self.lock:
            result = {
                "info": copy.deepcopy(self._analysis_data),
                "fen": copy.deepcopy(self.current_game.fen()),
                "game": self.current_game_id,
            }
            return result

    async def update_game(self, new_game: chess.Board):
        """Updates the position for analysis. The game id is still the same"""
        async with self.lock:
            self.game = new_game.copy()  # remember this game position
            self.limit_reached = False  # True when limit reached for position
            # dont reset self._analysis_data to None
            # let the main loop self._analyze_position manage it

    def is_running(self) -> bool:
        """
        Checks if the analysis is running.

        :return: True if analysis is running, otherwise False.
        """
        return self._running

    def get_current_game(self) -> Optional[chess.Board]:
        """
        Retrieves the current board being analyzed.

        :return: A copy of the current chess board or None if no board is set.
        """
        return self.current_game.copy() if self.current_game else None


class UciEngine(object):
    """Handle the uci engine communication."""

    # The rewrite for the new python chess module:
    # This UciEngine class can be in two modes:
    # WATCHING = user plays both sides
    # - an analysis generator to ask latest info is running
    #   in this mode you can send multipv larger than zero
    #   which is what the PicoTutor instance will do
    #   in PicoTutor the PicoTutor engine is not playing
    #   its just watching
    # PLAYING = user plays against computer
    # - self.res is no longer used
    # - self.pondering indicates if engine is to ponder
    #   without pondering analysis will be "static" one-timer

    def __init__(
        self,
        file: str,
        uci_shell: UciShell,
        mame_par: str,
        loop: asyncio.AbstractEventLoop,
        engine_debug_name: str = "engine",
    ):
        """initialise engine with file and mame_par info"""
        super(UciEngine, self).__init__()
        logger.info("mame parameters=%s", mame_par)
        self.pondering = False  # normal mode no pondering
        self.loop = loop  # main loop everywhere
        self.analyser: ContinuousAnalysis | None = None
        # previous existing attributes:
        self.is_adaptive = False
        self.engine_rating = -1
        self.uci_elo_eval_fn = None  # saved UCI_Elo eval function
        self.file = file
        self.mame_par = mame_par
        self.is_mame = "/mame/" in self.file
        self.transport = None  # find out correct type
        self.engine: UciProtocol | None = None
        self.engine_name = "NN"
        self.eng_long_name = "NN"
        self.options: dict = {}
        self.res: PlayResult = None
        self.level_support = False
        self.shell = None  # check if uci files can be used any more
        self.whoami = engine_debug_name
        self.engine_lock = asyncio.Lock()

    async def open_engine(self):
        """Open engine. Call after __init__"""
        try:
            logger.info("file %s", self.file)
            if self.is_mame:
                mfile = [self.file, self.mame_par]
            else:
                mfile = [self.file]
            logger.info("mfile %s", mfile)
            logger.info("opening engine")
            self.transport, self.engine = await chess.engine.popen_uci(mfile)
            self.analyser = ContinuousAnalysis(
                engine=self.engine, delay=FLOAT_ANALYSIS_WAIT, loop=self.loop, engine_debug_name=self.whoami
            )
            if self.engine:
                if "name" in self.engine.id:
                    self.engine_name = self.eng_long_name = self.engine.id["name"]
                    i = self.engine_name.find(" ")
                    if i != -1:
                        self.engine_name = self.engine_name[:i]
            else:
                logger.error("engine executable %s not found", self.file)
        except OSError:
            logger.exception("OS error in starting engine %s", self.file)
        except TypeError:
            logger.exception("engine executable not found %s", self.file)
        except chess.engine.EngineTerminatedError:
            logger.exception("engine terminated - could not execute file %s", self.file)

    def loaded_ok(self) -> bool:
        """check if engine was loaded ok"""
        return self.engine is not None

    def get_name(self) -> str:
        """Get engine display name. Shorter version"""
        return self.engine_name

    def get_long_name(self) -> str:
        """Get full engine name - usually contains version info"""
        return self.eng_long_name

    def get_options(self):
        """Get engine options."""
        return self.options

    def get_pgn_options(self):
        """Get options."""
        return self.options

    def option(self, name: str, value):
        """Set OptionName with value."""
        self.options[name] = value

    async def send(self):
        """Send options to engine."""
        try:
            await self.engine.configure(self.options)
            try:
                await self.engine.ping()  # send isready and wait for answer
            except CancelledError:
                logger.debug("ping isready cancelled - we are probably closing down")
        except chess.engine.EngineError as e:
            logger.warning(e)

    def has_levels(self):
        """Return engine level support."""
        has_lv = self.has_skill_level() or self.has_handicap_level() or self.has_limit_strength() or self.has_strength()
        return self.level_support or has_lv

    def has_skill_level(self):
        """Return engine skill level support."""
        return "Skill Level" in self.engine.options

    def has_handicap_level(self):
        """Return engine handicap level support."""
        return "Handicap Level" in self.engine.options

    def has_limit_strength(self):
        """Return engine limit strength support."""
        return "UCI_LimitStrength" in self.engine.options

    def has_strength(self):
        """Return engine strength support."""
        return "Strength" in self.engine.options

    def has_chess960(self):
        """Return chess960 support."""
        return "UCI_Chess960" in self.engine.options

    def has_ponder(self):
        """Return ponder support."""
        return "Ponder" in self.engine.options

    def get_file(self):
        """Get File."""
        return self.file

    async def quit(self):
        """Quit engine."""
        if self.analyser.is_running():
            self.analyser.cancel()  # quit can force full cancel
        await self.engine.quit()  # Ask nicely
        # @todo not sure how to know if we can call terminate and kill?
        if self.is_mame:
            os.system("sudo pkill -9 -f mess")

    def stop(self):
        """Stop background ContinuousAnalyser and/or force engine to move"""
        self.stop_analysis()
        if not self.is_waiting():
            self.force_move()

    def stop_analysis(self):
        """Stop background ContinuousAnalyser"""
        if self.analyser.is_running():
            self.analyser.cancel()  # @todo - find out why we need cancel and not stop

    def force_move(self):
        """Force engine to move - only call this when engine not waiting"""
        if self.engine:
            logger.debug("forcing engine to make a move")
            # new chess lib does not have a stop call
            self.engine.send_line("stop")

    def pause_pgn_audio(self):
        """Stop engine."""
        logger.info("pause audio old")
        # this is especially for pgn_engine
        self.engine.send_line("stop")

    def get_engine_limit(self, time_dict: dict) -> Limit:
        """convert time_dict to engine Limit for engine thinking"""
        max_time = None
        try:
            logger.debug("molli: timedict: %s", str(time_dict))
            if "movestogo" in time_dict:
                moves = int(time_dict["movestogo"])
            else:
                moves = None
            if "wtime" in time_dict:
                white_t = float(time_dict["wtime"]) / 1000.0
            elif "movetime" in time_dict:
                # send max_time to search exactly N seconds
                white_t = None
                max_time = float(time_dict["movetime"]) / 1000.0
            else:
                white_t = FLOAT_MAX_ENGINE_TIME  # fallback
                logger.warning("engine using fallback time for white")
            if "btime" in time_dict:
                black_t = float(time_dict["btime"]) / 1000.0
            elif "movetime" in time_dict:
                # send max_time to search exactly N seconds
                black_t = None
                max_time = float(time_dict["movetime"]) / 1000.0
            else:
                black_t = FLOAT_MAX_ENGINE_TIME  # fallback
                logger.warning("engine using fallback time for black")
            white_inc = float(time_dict["winc"]) / 1000.0 if "winc" in time_dict else None
            black_inc = float(time_dict["binc"]) / 1000.0 if "binc" in time_dict else None
        except ValueError:
            logger.warning("wrong thinking times sent to engine, using fallback")
            white_t = black_t = FLOAT_MAX_ENGINE_TIME
            white_inc = black_inc = 0
        use_time = Limit(
            time=max_time,
            white_clock=white_t,
            black_clock=black_t,
            white_inc=white_inc,
            black_inc=black_inc,
            remaining_moves=moves,
        )
        return use_time

    async def go(
        self, time_dict: dict, game: Board, result_queue: asyncio.Queue, root_moves: Optional[Iterable[chess.Move]]
    ) -> None:
        """Go engine.
        parameter game will not change, it is deep copied"""
        if self.engine:
            async with self.engine_lock:
                limit: Limit = self.get_engine_limit(time_dict)
                await self.analyser.play_move(
                    game, limit=limit, ponder=self.pondering, result_queue=result_queue, root_moves=root_moves
                )
        else:
            logger.error("go called but no engine loaded")

    async def start_analysis(self, game: chess.Board, limit: Limit | None = None, multipv: int | None = None) -> bool:
        """start analyser - returns True if if it was already running
        in current game position, which means result can be expected

        parameters:
        game: the game position to be analysed
        limit: limit for analysis - None means forever
        multipv: multipv for analysis - None means 1"""
        result = False
        if self.analyser.is_running():
            if limit and limit.depth != self.analyser.get_limit_depth():
                logger.debug("%s picotutor limit change: %d- mode/engine switch?", self.whoami, limit.depth)
                self.analyser.update_limit(limit)
            if game.fen() != self.analyser.get_fen():
                await self.analyser.update_game(game)  # new position
                logger.debug("%s new analysis position", self.whoami)
            else:
                result = True  # was running - results to be expected
                # logger.debug("continue with old analysis position")
        else:
            if self.engine:
                async with self.engine_lock:
                    self.analyser.start(game, limit=limit, multipv=multipv)
            else:
                logger.warning("start analysis requested but no engine loaded")
        return result

    def is_analyser_running(self) -> bool:
        """check if analyser is running"""
        return self.analyser.is_running()

    async def get_analysis(self, game: chess.Board) -> dict:
        """get analysis info from engine - returns dict with info and fen
        key 'info': list of InfoDict (multipv)
        key 'fen': analysed board position fen"""
        # failed answer is empty lists
        result = {"info": [], "fen": ""}
        if self.analyser.is_running():
            if self.analyser.get_fen() == game.fen():
                result = await self.analyser.get_analysis()
            else:
                logger.debug("analysis for old position")
                logger.debug("current new position is %s", game.fen())
        else:
            logger.debug("caller has forgot to start analysis")
        return result

    def is_analysis_limit_reached(self) -> bool:
        """return True if limit was reached for position being analysed"""
        if self.analyser.is_running():
            return self.analyser.is_limit_reached()
        return False

    # this function was taken out of use after introduction
    # of the new analyser ContinuousAnalysis
    async def playmode_analyse(
        self,
        game: Board,
        limit: Limit,
    ) -> InfoDict | None:
        """Get analysis update from playing engine
        might block if engine is thinking to protect chess library"""
        try:
            async with self.engine_lock:
                info = await self.engine.analyse(copy.deepcopy(game), limit)
        except chess.engine.EngineTerminatedError:
            logger.error("Engine terminated")  # @todo find out, why this can happen!
            info = None
        return info

    def is_thinking(self):
        """Engine thinking."""
        # @ todo check if self.pondering should be removed
        return not self.analyser.is_idle()

    def is_pondering(self):
        """Engine pondering."""
        # in the new chess module we are possibly idle
        # but have to inform picochess.py that we could
        # be pondering anyway
        return self.pondering

    def is_waiting(self):
        """Engine waiting."""
        return self.analyser.is_idle()

    def is_ready(self):
        """Engine waiting."""
        return True  # should not be needed any more

    async def newgame(self, game: Board, send_ucinewgame: bool = True):
        """Engine sometimes need this to setup internal values.
        parameter game will not change"""
        if self.engine:
            async with self.engine_lock:
                # as seen in issue #78 need to prevent simultaneous newgame and start analysis
                self.analyser.newgame()  # chess lib signals ucinewgame in next call to engine
                await self.analyser.update_game(game)  # both these lines causes analyser to stop nicely
                await asyncio.sleep(0.3)  # wait for analyser to stop
                # @todo we could wait for ping() isready here - but it could break pgn_engine logic
                # do not self.engine.send_line("ucinewgame"), see read_pgn_file in picochess.py
                # it will confuse the engine when switching between playing/non-playing modes
                # but: issue #72 at least mame engines need ucinewgame to be sent
                # we force it here and to avoid breaking read_pgn_file I added a default parameter
                # due to errors with readyok response crash issue #78 restrict to mame
                if self.is_mame and send_ucinewgame:
                    # most calls except read_pgn_file newgame, and load new engine
                    logger.debug("sending ucinewgame to engine")
                    self.engine.send_line("ucinewgame")  # force ucinewgame to engine
        else:
            logger.error("newgame requested but no engine loaded")

    def set_mode(self, ponder: bool = True):
        """Set engine ponder mode for a playing engine"""
        self.pondering = ponder  # True in BRAIN mode = Ponder On menu

    async def startup(self, options: dict, rating: Optional[Rating] = None):
        """Startup engine."""
        parser = configparser.ConfigParser()

        if not options:
            if self.shell is None:
                success = bool(parser.read(self.get_file() + ".uci"))
            else:
                try:
                    with self.shell.open(self.get_file() + ".uci", "r") as file:
                        parser.read_file(file)
                    success = True
                except FileNotFoundError:
                    success = False
            if success:
                options = dict(parser[parser.sections().pop()])

        self.level_support = bool(options)

        self.options = options.copy()
        self._engine_rating(rating)
        logger.debug("setting engine with options %s", self.options)
        await self.send()

        logger.debug("Loaded engine [%s]", self.get_name())
        logger.debug("Supported options [%s]", self.get_options())

    def _engine_rating(self, rating: Optional[Rating] = None):
        """
        Set engine_rating; replace UCI_Elo 'auto' value with rating.
        Delete UCI_Elo from the options if no rating is given.
        """
        uci_elo_option_string = None
        if UCI_ELO in self.options:
            uci_elo_option_string = UCI_ELO
        elif UCI_ELO_NON_STANDARD in self.options:
            uci_elo_option_string = UCI_ELO_NON_STANDARD
        elif UCI_ELO_NON_STANDARD2 in self.options:
            uci_elo_option_string = UCI_ELO_NON_STANDARD2
        if uci_elo_option_string is not None:
            uci_elo_option = self.options[uci_elo_option_string].strip()
            if uci_elo_option.lower() == "auto" and rating is not None:
                self._set_rating(self._round_engine_rating(int(rating.rating)))
            elif uci_elo_option.isnumeric():
                self.engine_rating = int(uci_elo_option)
            elif "auto" in uci_elo_option and rating is not None:
                uci_elo_with_rating = uci_elo_option.replace("auto", str(int(rating.rating)))
                try:
                    evaluated = eval(uci_elo_with_rating)
                    if str(evaluated).isnumeric():
                        self._set_rating(int(evaluated))
                        self.uci_elo_eval_fn = uci_elo_option  # save evaluation function for updating engine ELO later
                    else:
                        del self.options[uci_elo_option_string]
                except Exception as e:  # noqa - catch all exceptions for eval()
                    logger.error(f"invalid option set for {uci_elo_option_string}={uci_elo_with_rating}, exception={e}")
                    del self.options[uci_elo_option_string]
            else:
                del self.options[uci_elo_option_string]

    def _set_rating(self, value: int):
        self.engine_rating = value
        self._set_uci_elo_to_engine_rating()
        self.is_adaptive = True

    def _round_engine_rating(self, value: int) -> int:
        """Round the value up to the next 50, minimum=500"""
        return max(500, int(value / 50 + 1) * 50)

    async def update_rating(self, rating: Rating, result: Result) -> Rating:
        """Send the new ELO value to the engine and save the ELO and rating deviation"""
        if not self.is_adaptive or result is None or self.engine_rating < 0:
            return rating
        new_rating = rating.rate(Rating(self.engine_rating, 0), result)
        if self.uci_elo_eval_fn is not None:
            # evaluation function instead of auto?
            self.engine_rating = eval(self.uci_elo_eval_fn.replace("auto", str(int(new_rating.rating))))
        else:
            self.engine_rating = self._round_engine_rating(int(new_rating.rating))
        self._save_rating(new_rating)
        self._set_uci_elo_to_engine_rating()
        await self.send()
        return new_rating

    def _set_uci_elo_to_engine_rating(self):
        if UCI_ELO in self.options:
            self.options[UCI_ELO] = str(int(self.engine_rating))
        elif UCI_ELO_NON_STANDARD in self.options:
            self.options[UCI_ELO_NON_STANDARD] = str(int(self.engine_rating))
        elif UCI_ELO_NON_STANDARD2 in self.options:
            self.options[UCI_ELO_NON_STANDARD2] = str(int(self.engine_rating))

    def _save_rating(self, new_rating: Rating):
        write_picochess_ini("pgn-elo", max(500, int(new_rating.rating)))
        write_picochess_ini("rating-deviation", int(new_rating.rating_deviation))
