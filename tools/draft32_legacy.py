"""Доски драфта NHL Legacy на 32 клуба: три колонки 1–15 | 16–30 | 31–32 — файлы для cache: Legacy.

    python draft32_legacy.py build [--work DIR] [--no-out] [--all]
        # → WORK (game/work/legacy-data/draft32/build, раскладка cache:) — все 5 досок; в game/work/legacy-data/out —
        #   только доски с 'out': True в SCREENS (проверенные в игре; --all — все 5); список того, что в out, —
        #   game/work/legacy-data/draft32/files.txt; разбор нового кода — WORK/review/*.txt
    python draft32_legacy.py check [DIR]     # собранное: ролики разбираются, старая часть Apt Data — только правки
                                             # из списка, третья панель на месте, новый код без ошибок разбора

Разбор (11.10.2026, docs/fe-menu-legacy.md §11): доски драфта — пять роликов с двумя панелями по 15 строк
(MAX_TEAMS_PER_PANEL = 15 в ActionScript, игра отдаёт 32 клуба — у правой 17 строк данных при 15 видимых, две
последние не видно). Правка — третья панель как у EA (тот же символ панели, RowControl, строки 24, шрифты и
логотипы те же), колонки по 325 вместо 494:
  * PlaceObject: правая панель x 646 → 477, новая третья x 802 (у Live the Life — внутри спрайта экрана);
  * строка: поле имени (txtPlayerName/txtTeamName/txtName) и заголовок колонки — ширина до 325 (как в макете);
  * полоса выделения (Highlight ×1,53 = 459) → ×1,0433 = 313;
  * ActionScript: функции, где было «левая/правая», — с тремя панелями (смещение панели 0/15/30, выбор панели по
    номеру выбора, прокрутка и выделение — тем же RowControl; на экране порядка фэнтези-драфта ←/→ и ↑/↓ ходят по
    трём колонкам по кругу). Новый код — tools/aptc.py: блок кода кадра (у Live the Life — InitAction класса)
    пересобирается целиком, функции EA заменяются на месте, остальное — байт в байт; старый блок остаётся мёртвым.
Без кодогена и без exe: только ролики в cache:. Сиэтл и Вегас на досках есть и без этого (игра отдаёт 32), правка —
только видимость 31–32.

Только стандартная библиотека. Байткод — tools/feapt.py (разбор), tools/aptc.py (компилятор и пересборка блоков).
"""
import json, os, shutil, struct, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import aptc                # noqa: E402
import feapt               # noqa: E402
import febg                # noqa: E402
import gameprofile         # noqa: E402

P = gameprofile.get('legacy')
WORK = P.work_dir('draft32', 'build')
FILES = P.work_dir('draft32', 'files.txt')
ph = feapt.ph

COL_W = 325                      # колонка: (1128 − 152) / 3, панели x 152 | 477 | 802
X_RIGHT, X_THIRD = 477, 802
HL_SCALE = 313 / 300             # Highlight stdControls 300 → полоса 313 (у EA 1,53 × 300 = 459)
HL_SCALE_EA = 1.53

# ---------------------------------------------------------------- ActionScript: общие функции кадра

HELPERS = r'''
function draft32PanelOffset(mc) {
    if (mc == {R}) {
        return MAX_TEAMS_PER_PANEL;
    }
    if (mc == {T}) {
        return 2 * MAX_TEAMS_PER_PANEL;
    }
    return 0;
}
function draft32PanelFor(index) {
    if (index < MAX_TEAMS_PER_PANEL) {
        return {L};
    }
    if (index < 2 * MAX_TEAMS_PER_PANEL) {
        return {R};
    }
    return {T};
}
'''

INIT_PANELS_GM = r'''
function initPanels() {
    var n = m_arrDraftTeamIDs.length;
    trace("initPanels: m_arrDraftTeamIDs.length = " + n);
    var left = n;
    if (left > MAX_TEAMS_PER_PANEL) {
        left = MAX_TEAMS_PER_PANEL;
    }
    var right = n - left;
    if (right > MAX_TEAMS_PER_PANEL) {
        right = MAX_TEAMS_PER_PANEL;
    }
    initPanel(mcLeftPanel, 0, left);
    initPanel(mcRightPanel, MAX_TEAMS_PER_PANEL, right);
    initPanel(mcThirdPanel, 2 * MAX_TEAMS_PER_PANEL, n - left - right);
    updateHighlight();
}
'''

HIGHLIGHT_ROW_GM = r'''
function highlightRow(mcPanel, row, index) {
    var color;
    if (mcPanel == m_activePanel) {
        row.txtRank.textColor = _global.TEXT_COLOR.{SEL};
        row.txtPlayerName.textColor = _global.TEXT_COLOR.{SEL};
        color = _global.TEXT_COLOR.{SEL};
    } else {
        row.txtRank.textColor = _global.TEXT_COLOR.REGULAR;
        row.txtPlayerName.textColor = _global.TEXT_COLOR.REGULAR;
        color = _global.TEXT_COLOR.REGULAR;
    }
    if (m_activePanel != null) {
        m_activePanel.mcHighlight._x = HIGHLIGHT_OFFSET;
    }
    if (m_draftManager.isUserTeam(m_arrDraftTeamIDs[index + draft32PanelOffset(mcPanel)])) {
        var c = new Color(row.mcUserIcon);
        c.setRGB(color);
    }
}
'''

UPDATE_GUI_GM = r'''
function updateGUI() {
    updateDraftData();
    mcLeftPanel.rcTeams.refresh();
    mcRightPanel.rcTeams.refresh();
    mcThirdPanel.rcTeams.refresh();
    updateHighlight();
    _global.gHelpManager.ContextSwitch();
}
'''

# Be a GM — NHL Entry Draft (dm38_nhlentrydraft): выбор игрока, подсветка, смена раунда
CODE_ENTRY = {
    'helpers': HELPERS,
    'replace': {
        'initPanels': INIT_PANELS_GM,
        'highlightRow': HIGHLIGHT_ROW_GM.replace('{SEL}', 'LIGHT_GREY'),
        'updateGUI': UPDATE_GUI_GM,
        'pickPlayer': r'''
function pickPlayer() {
    var teamID = m_arrDraftTeamIDs[m_activePanel.rcTeams.getSelectedIndex() + draft32PanelOffset(m_activePanel)];
    var ctx = new Object();
    ctx.draftTeamID = teamID;
    _global.EA_ZONE.gSM.setContextDataObject(ctx, _global.SCREEN.DYNASTY.DM_ENTRY_DRAFT);
    m_draftManager.clearAllEventCallbacks();
    m_draftManager = null;
    _global.EA_ZONE.gSM.changeMainScreen(_global.SCREEN.DYNASTY.DM_SCOUTING_REPORT);
}
''',
        'unhighlightRow': r'''
function unhighlightRow(mcPanel, row, index) {
    row.txtRank.textColor = _global.TEXT_COLOR.REGULAR;
    row.txtPlayerName.textColor = _global.TEXT_COLOR.REGULAR;
    if (m_draftManager.isUserTeam(m_arrDraftTeamIDs[index + draft32PanelOffset(mcPanel)])) {
        var c = new Color(row.mcUserIcon);
        c.setRGB(_global.TEXT_COLOR.REGULAR);
    }
}
''',
        'updateHighlight': r'''
function updateHighlight() {
    if (m_activePanel != null && m_activePanel.rcTeams.getHighlightedRow() != null) {
        unhighlightRow(m_activePanel, m_activePanel.rcTeams.getHighlightedRow(), m_activePanel.rcTeams.getSelectedIndex());
    }
    mcLeftPanel.mcHighlight._visible = false;
    mcRightPanel.mcHighlight._visible = false;
    mcThirdPanel.mcHighlight._visible = false;
    if (togRound.getValue() != m_currentRound || m_arrDraftedPlayerNames.length == m_arrDraftTeamIDs.length) {
        m_activePanel = null;
        return;
    }
    var n = m_arrDraftedPlayerNames.length;
    m_activePanel = draft32PanelFor(n);
    m_activePanel.mcHighlight._visible = true;
    m_activePanel.rcTeams.setSelectedIndex(n - draft32PanelOffset(m_activePanel));
    if (m_bIsUserPick) {
        m_activePanel.mcHighlight.buttonA._visible = true;
    } else {
        m_activePanel.mcHighlight.buttonA._visible = false;
    }
}
''',
    },
    'splice': [('initGUI_3', 'addItem'), ],
}

# фэнтези-драфт (gamemode/fantasydraft): то же, но подсветка SELECTED, m_isUserPick, m_highlightedTeamID;
# unhighlightRow смещения панели не берёт (только m_highlightedTeamID) — не трогается
CODE_FANTASY = {
    'helpers': HELPERS,
    'replace': {
        'initPanels': INIT_PANELS_GM,
        'highlightRow': HIGHLIGHT_ROW_GM.replace('{SEL}', 'SELECTED'),
        'updateGUI': UPDATE_GUI_GM,
        'updateHighlight': r'''
function updateHighlight() {
    if (m_activePanel != null) {
        var row = m_activePanel.rcTeams.getHighlightedRow();
        if (row != null) {
            unhighlightRow(m_activePanel, row, m_activePanel.rcTeams.getSelectedIndex());
        }
    }
    mcLeftPanel.mcHighlight._visible = false;
    mcRightPanel.mcHighlight._visible = false;
    mcThirdPanel.mcHighlight._visible = false;
    if (togRound.getValue() != m_currentRound || m_arrDraftedPlayerNames.length == m_arrDraftTeamIDs.length) {
        m_activePanel = null;
        return;
    }
    var n = m_arrDraftedPlayerNames.length;
    m_activePanel = draft32PanelFor(n);
    m_activePanel.mcHighlight._visible = true;
    m_activePanel.rcTeams.setSelectedIndex(n - draft32PanelOffset(m_activePanel));
    m_highlightedTeamID = m_arrDraftTeamIDs[n];
    if (m_isUserPick) {
        m_activePanel.mcHighlight.buttonA._visible = true;
    } else {
        m_activePanel.mcHighlight.buttonA._visible = false;
    }
}
''',
    },
    'splice': [('initGUI_3', 'addItem')],
}

# порядок фэнтези-драфта (gamemode/draftorder): курсор ходит сам — ↑/↓ по колонке и дальше в соседнюю,
# ←/→ — в соседнюю колонку (по кругу 1 → 2 → 3 → 1), Y — обмен двух клубов местами
CODE_ORDER = {
    'helpers': HELPERS + r'''
function draft32NextPanel(mc, dir) {
    var count = 1;
    if (m_arrTeamIDs.length > MAX_TEAMS_PER_PANEL) {
        count = 2;
    }
    if (m_arrTeamIDs.length > 2 * MAX_TEAMS_PER_PANEL) {
        count = 3;
    }
    var i = 0;
    if (mc == mcRightPanel) {
        i = 1;
    }
    if (mc == mcThirdPanel) {
        i = 2;
    }
    if (dir < 0) {
        i = i - 1;
    } else {
        i = i + 1;
    }
    if (i < 0) {
        i = count - 1;
    }
    if (i >= count) {
        i = 0;
    }
    if (i == 1) {
        return mcRightPanel;
    }
    if (i == 2) {
        return mcThirdPanel;
    }
    return mcLeftPanel;
}
''',
    'replace': {
        'initPanels': r'''
function initPanels() {
    var n = m_arrTeamIDs.length;
    var left = n;
    if (left > MAX_TEAMS_PER_PANEL) {
        left = MAX_TEAMS_PER_PANEL;
    }
    var right = n - left;
    if (right > MAX_TEAMS_PER_PANEL) {
        right = MAX_TEAMS_PER_PANEL;
    }
    m_activePanel = mcLeftPanel;
    initPanel(mcLeftPanel, 0, left);
    initPanel(mcRightPanel, MAX_TEAMS_PER_PANEL, right);
    initPanel(mcThirdPanel, 2 * MAX_TEAMS_PER_PANEL, n - left - right);
    mcLeftPanel.mcHighlight._visible = true;
    mcRightPanel.mcHighlight._visible = false;
    mcThirdPanel.mcHighlight._visible = false;
}
''',
        'highlightRow': r'''
function highlightRow(mcPanel, row, index) {
    var color;
    if (mcPanel == m_activePanel) {
        row.txtRank.textColor = _global.TEXT_COLOR.SELECTED;
        row.txtTeamName.textColor = _global.TEXT_COLOR.SELECTED;
        color = _global.TEXT_COLOR.SELECTED;
    } else {
        row.txtRank.textColor = _global.TEXT_COLOR.REGULAR;
        row.txtTeamName.textColor = _global.TEXT_COLOR.REGULAR;
        color = _global.TEXT_COLOR.REGULAR;
    }
    if (isUserTeam(m_arrTeamIDs[index + draft32PanelOffset(mcPanel)])) {
        var c = new Color(row.mcUserIcon);
        c.setRGB(color);
    }
    m_activePanel.mcHighlight._x = HIGHLIGHT_OFFSET;
    if (m_selectedTeamPanel != null && m_selectedTeamPanelIndex != NO_TEAM_SELECTED) {
        if (mcPanel != m_selectedTeamPanel || m_selectedTeamPanelIndex != index) {
            m_selectedTeamPanel.rcTeams.showAlternateHighlight(m_selectedTeamPanelIndex);
        } else {
            mcPanel.rcTeams.clearAlternateHighlight();
        }
    }
}
''',
        'unhighlightRow': r'''
function unhighlightRow(mcPanel, row, index) {
    if (mcPanel == m_selectedTeamPanel && index == m_selectedTeamPanelIndex) {
        return;
    }
    row.txtRank.textColor = _global.TEXT_COLOR.REGULAR;
    row.txtTeamName.textColor = _global.TEXT_COLOR.REGULAR;
    if (isUserTeam(m_arrTeamIDs[index + draft32PanelOffset(mcPanel)])) {
        var c = new Color(row.mcUserIcon);
        c.setRGB(_global.TEXT_COLOR.REGULAR);
    }
}
''',
        'completeSwapOperation': r'''
function completeSwapOperation() {
    var a = m_selectedTeamPanelIndex + draft32PanelOffset(m_selectedTeamPanel);
    var b = m_activePanel.rcTeams.getSelectedIndex() + draft32PanelOffset(m_activePanel);
    if (a != b) {
        var t = m_arrTeamIDs[a];
        m_arrTeamIDs[a] = m_arrTeamIDs[b];
        m_arrTeamIDs[b] = t;
        t = m_arrTeamAttrib[a];
        m_arrTeamAttrib[a] = m_arrTeamAttrib[b];
        m_arrTeamAttrib[b] = t;
        updateRow(draft32PanelOffset(m_selectedTeamPanel), m_selectedTeamPanel.rcTeams.getRowAtIndex(m_selectedTeamPanelIndex), m_selectedTeamPanelIndex);
        updateRow(draft32PanelOffset(m_activePanel), m_activePanel.rcTeams.getHighlightedRow(), m_activePanel.rcTeams.getSelectedIndex());
    }
    endSwapOperation();
}
''',
        'navigateUp': r'''
function navigateUp() {
    if (m_activePanel.rcTeams.getSelectedIndex() != 0) {
        m_activePanel.rcTeams.previous();
    } else {
        if (m_arrTeamIDs.length > MAX_TEAMS_PER_PANEL) {
            switchActivePanel(-1);
        }
        m_activePanel.rcTeams.setSelectedIndex(getPanelLastIndex(m_activePanel));
    }
}
''',
        'navigateDown': r'''
function navigateDown() {
    if (m_activePanel.rcTeams.getSelectedIndex() != getPanelLastIndex(m_activePanel)) {
        m_activePanel.rcTeams.next();
    } else {
        if (m_arrTeamIDs.length > MAX_TEAMS_PER_PANEL) {
            switchActivePanel(1);
        }
        m_activePanel.rcTeams.setSelectedIndex(0);
    }
}
''',
        'navigateLeftRight': r'''
function navigateLeftRight(dir) {
    if (!(m_arrTeamIDs.length > MAX_TEAMS_PER_PANEL)) {
        return;
    }
    var idx = m_activePanel.rcTeams.getSelectedIndex();
    switchActivePanel(dir);
    var last = getPanelLastIndex(m_activePanel);
    if (idx > last) {
        m_activePanel.rcTeams.setSelectedIndex(last);
    } else {
        m_activePanel.rcTeams.setSelectedIndex(idx);
    }
    _global.playSound(_global.GameServices.eSoundEvent.IMMEDIATE_MOVE_CURSOR);
}
''',
        'switchActivePanel': r'''
function switchActivePanel(dir) {
    m_activePanel.mcHighlight._visible = false;
    unhighlightRow(m_activePanel, m_activePanel.rcTeams.getHighlightedRow(), m_activePanel.rcTeams.getSelectedIndex());
    m_activePanel = draft32NextPanel(m_activePanel, dir);
    m_activePanel.mcHighlight._visible = true;
}
''',
        'getPanelLastIndex': r'''
function getPanelLastIndex(mcPanel) {
    var n = m_arrTeamIDs.length - draft32PanelOffset(mcPanel);
    if (n > MAX_TEAMS_PER_PANEL) {
        n = MAX_TEAMS_PER_PANEL;
    }
    return n - 1;
}
''',
        'localEventHandler': r'''
function localEventHandler(keyCode, controllerId) {
    if (keyCode === _global.INPUTCODE.UI_UP) {
        navigateUp();
    } else if (keyCode === _global.INPUTCODE.UI_DOWN) {
        navigateDown();
    } else if (keyCode === _global.INPUTCODE.UI_LEFT) {
        navigateLeftRight(-1);
    } else if (keyCode === _global.INPUTCODE.UI_RIGHT) {
        navigateLeftRight(1);
    } else if (keyCode === _global.INPUTCODE.ADVANCE) {
        if (m_selectedTeamPanelIndex == NO_TEAM_SELECTED) {
            advanceScreen();
        }
    } else if (keyCode === _global.INPUTCODE.BACK) {
        if (m_selectedTeamPanelIndex == NO_TEAM_SELECTED) {
            backScreen();
        } else {
            endSwapOperation();
        }
    } else if (keyCode === _global.INPUTCODE.OPTION_LEFT) {
        if (m_selectedTeamPanelIndex == NO_TEAM_SELECTED) {
            randomizeDraftOrder();
        }
    } else if (keyCode === _global.INPUTCODE.OPTION_TOP) {
        _global.playSound(_global.GameServices.eSoundEvent.PRIMARY_SELECT);
        if (m_selectedTeamPanelIndex == NO_TEAM_SELECTED) {
            initSwapOperation();
        } else {
            completeSwapOperation();
        }
    } else if (keyCode === _global.INPUTCODE.SELECT) {
        _global.gHelpManager.ShowHelpPopup();
    }
}
''',
    },
    'splice': [('initGUI_3', 'addItem'), ('randomizeDraftOrder', 'refresh')],
}

# Live the Life — день драфта (pro/draftday): курсора нет, подсветка идёт за текущим выбором
CODE_DRAFTDAY = {
    'helpers': '',
    'replace': {
        'initGUI_2': r'''
function initGUI_2() {
    trace(TRACE_TAG + "initGUI_2");
    m_nhlLeagueID = _global.ION_League.GetIDs(_global.League.eFilter.FILTER_NHL, _global.League.eSortColumn.SORT_NONE, _global.GameServices.eSortType.SORT_UNSORTED)[0];
    initHeader();
    initTeamData();
    var n = m_arrTeamIds.length;
    var left = n;
    if (left > MAX_TEAMS_PER_PANEL) {
        left = MAX_TEAMS_PER_PANEL;
    }
    var right = n - left;
    if (right > MAX_TEAMS_PER_PANEL) {
        right = MAX_TEAMS_PER_PANEL;
    }
    m_activePanel = mcLeft;
    initPanel(mcLeft, 0, left);
    initPanel(mcRight, MAX_TEAMS_PER_PANEL, right);
    initPanel(mcThird, 2 * MAX_TEAMS_PER_PANEL, n - left - right);
    mcLeft.mcHighlight._visible = true;
    mcRight.mcHighlight._visible = false;
    mcThird.mcHighlight._visible = false;
}
''',
        'updateHighlight': r'''
function updateHighlight() {
    var panel = null;
    var idx = -1;
    if (m_numDraftedPlayers < m_arrTeamIds.length) {
        if (m_numDraftedPlayers < MAX_TEAMS_PER_PANEL) {
            panel = mcLeft;
            idx = m_numDraftedPlayers;
        } else if (m_numDraftedPlayers < 2 * MAX_TEAMS_PER_PANEL) {
            panel = mcRight;
            idx = m_numDraftedPlayers - MAX_TEAMS_PER_PANEL;
        } else {
            panel = mcThird;
            idx = m_numDraftedPlayers - 2 * MAX_TEAMS_PER_PANEL;
        }
    }
    if (m_activePanel != panel) {
        if (m_activePanel != null) {
            unHighlightPanel();
        }
        m_activePanel = panel;
        if (m_activePanel != null) {
            m_activePanel.mcHighlight._visible = true;
            m_activePanel.rc.setSelectedIndex(idx);
        } else {
            m_activePanel.mcHighlight._visible = false;
        }
    } else {
        if (m_activePanel != null) {
            m_activePanel.rc.setSelectedIndex(idx);
        }
    }
}
''',
    },
    'splice': [('initGUI_3', 'addItem'), ('cbRoundChange', 'refresh'), ('cbRoundSimComplete', 'refresh')],
}

# Live the Life — драфт (pro/beaproentrydraft): класс game.screens.pro.BeAProEntryDraft (InitAction спрайта 21)
CLS = 'game.screens.pro.BeAProEntryDraft'
CODE_BAP = {
    'methods': {
        '_InitializeScreen': r'''
function () {
    trace(game.screens.pro.BeAProEntryDraft.TRACE_TAG + "_InitializeScreen");
    this.mainFrame.setTitle(_global.gGetTitleForCurrentState(), _global.ltxt("TXT_DRAFT_DAY"));
    this._InitHeader();
    this._InitTeamData();
    var max = game.screens.pro.BeAProEntryDraft.MAX_TEAMS_PER_PANEL;
    var n = this.mArrTeamIds.length;
    var left = n;
    if (left > max) {
        left = max;
    }
    var right = n - left;
    if (right > max) {
        right = max;
    }
    this.mNumPlayersLeftPanel = left;
    this.mNumPlayersRightPanel = right;
    this.mNumPlayersThirdPanel = n - left - right;
    this.mActivePanel = this.mcLeft;
    this._InitPanel(this.mcLeft, cafe.utility.Delegate.Create(this, this._OnUpdateLeftPanelRow), cafe.utility.Delegate.Create(this, this._OnHighlightLeftPanelRow), this.mNumPlayersLeftPanel);
    this._InitPanel(this.mcRight, cafe.utility.Delegate.Create(this, this._OnUpdateRightPanelRow), cafe.utility.Delegate.Create(this, this._OnHighlightRightPanelRow), this.mNumPlayersRightPanel);
    this._InitPanel(this.mcThird, cafe.utility.Delegate.Create(this, this._OnUpdateThirdPanelRow), cafe.utility.Delegate.Create(this, this._OnHighlightThirdPanelRow), this.mNumPlayersThirdPanel);
    this.mcLeft.mcHighlight._visible = true;
    this.mcRight.mcHighlight._visible = false;
    this.mcThird.mcHighlight._visible = false;
}
''',
        # у EA смещение правой панели — mNumPlayersRightPanel (при 30 клубах = 15 случайно); теперь 15 всегда
        '_OnUpdateRightPanelRow': r'''
function (row, index) {
    this._UpdateRow(row, index, game.screens.pro.BeAProEntryDraft.MAX_TEAMS_PER_PANEL);
}
''',
        '_UpdateHighlight': r'''
function () {
    var max = game.screens.pro.BeAProEntryDraft.MAX_TEAMS_PER_PANEL;
    var panel = null;
    var idx = -1;
    var n = this.mNumDraftedPlayers;
    if (n < this.mArrTeamIds.length) {
        if (n < max) {
            panel = this.mcLeft;
            idx = n;
        } else if (n < 2 * max) {
            panel = this.mcRight;
            idx = n - max;
        } else {
            panel = this.mcThird;
            idx = n - 2 * max;
        }
    }
    if (this.mActivePanel != panel) {
        if (this.mActivePanel != null) {
            this._UnHighlightPanel();
        }
        this.mActivePanel = panel;
        if (this.mActivePanel != null) {
            this.mActivePanel.mcHighlight._visible = true;
            this.mActivePanel.rc.setSelectedIndex(idx);
        } else {
            this.mActivePanel.mcHighlight._visible = false;
        }
    } else {
        if (this.mActivePanel != null) {
            this.mActivePanel.rc.setSelectedIndex(idx);
        }
    }
}
''',
    },
    # новые методы — после определения _OnUpdateRightPanelRow
    'new_after': '_OnUpdateRightPanelRow',
    'new': r'''
game.screens.pro.BeAProEntryDraft.prototype._OnUpdateThirdPanelRow = function (row, index) {
    this._UpdateRow(row, index, 2 * game.screens.pro.BeAProEntryDraft.MAX_TEAMS_PER_PANEL);
};
game.screens.pro.BeAProEntryDraft.prototype._OnHighlightThirdPanelRow = function (row, index) {
    this._HighlightRow(this.mcThird, row, index);
};
''',
    'splice': [('_AnimateIn', 'addItem'), ('_OnRoundChange', 'refresh')],
}

# ---------------------------------------------------------------- экраны

# 'out': True — доска идёт в out (в cache: при установке legacy-data). 11.10.2026 в игре проверены Entry Draft и
# фэнтези-драфт с его порядком (падение фэнтези-драфта на 32 починено в exe nhl-legacy-port a1cb8f74); Live the Life — только
# по коду, в out не идёт
SCREENS = [
    {'rel': 'fe/ion/game/screens/dynasty/dm38_nhlentrydraft.big', 'what': 'Be a GM — NHL Entry Draft',
     'owner': 0, 'panels': ('mcLeftPanel', 'mcRightPanel', 'mcThirdPanel'), 'third_depth': 24, 'rc': 'rcTeams',
     'texts': {4: 'txtPlayerName', 17: 'txtPlayerTitle'}, 'highlights': [14], 'code': CODE_ENTRY, 'out': True},
    {'rel': 'fe/ion/game/screens/gamemode/fantasydraft.big', 'what': 'фэнтези-драфт',
     'owner': 0, 'panels': ('mcLeftPanel', 'mcRightPanel', 'mcThirdPanel'), 'third_depth': 24, 'rc': 'rcTeams',
     'texts': {4: 'txtPlayerName', 17: 'txtPlayerTitle'}, 'highlights': [14], 'code': CODE_FANTASY, 'out': True},
    {'rel': 'fe/ion/game/screens/gamemode/draftorder.big', 'what': 'порядок фэнтези-драфта',
     'owner': 0, 'panels': ('mcLeftPanel', 'mcRightPanel', 'mcThirdPanel'), 'third_depth': 30, 'rc': 'rcTeams',
     'texts': {4: 'txtTeamName', 19: 'txtTeamTitle'}, 'highlights': [14, 16], 'code': CODE_ORDER, 'out': True},
    {'rel': 'fe/ion/game/screens/pro/draftday.big', 'what': 'Live the Life — день драфта',
     'owner': 0, 'panels': ('mcLeft', 'mcRight', 'mcThird'), 'third_depth': 21, 'rc': 'rc',
     'texts': {4: 'txtName', 13: 'txtPlayerTitle'}, 'highlights': [14], 'code': CODE_DRAFTDAY, 'out': False},
    {'rel': 'fe/ion/game/screens/pro/beaproentrydraft.big', 'what': 'Live the Life — драфт',
     'owner': 18, 'panels': ('mcLeft', 'mcRight', 'mcThird'), 'third_depth': 21, 'rc': 'rc',
     'texts': {4: 'txtName', 13: 'txtPlayerTitle'}, 'highlights': [14], 'code': CODE_BAP, 'class_sprite': 21,
     'out': False},
]


def log(*a):
    print(*a, flush=True)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def p(root, rel):
    return os.path.join(root, *rel.split('/'))


def legacy_src(rel):
    f = P.extracted(rel)
    if not f:
        raise SystemExit(f'нет {rel} в распакованных архивах Legacy ({P.big})')
    return f


def u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


def f32(b, o):
    return struct.unpack_from('>f', b, o)[0]


# ---------------------------------------------------------------- правки Apt Data

class Edit:
    """Правки ролика: на месте (той же длины, со сверкой старых байт) и дописанное в конец."""

    def __init__(self, path):
        self.mv, self.consts = feapt.load_movie(path)
        self.apt = self.mv.apt
        self.d = bytearray(self.apt.data)
        self.orig_len = len(self.d)
        self.inplace = []           # (смещение, старые, новые, что)
        self.strings = {}

    def put(self, off, new, what):
        old = bytes(self.d[off:off + len(new)])
        self.d[off:off + len(new)] = new
        self.inplace.append((off, old, bytes(new), what))

    def place(self, owner, name):
        ch = self.apt.chars[owner]
        hits = [it for it in ch.frames[0] if it.po and it.po.name == name]
        if len(hits) != 1:
            raise SystemExit(f'символ {owner}: PlaceObject «{name}» — {len(hits)} шт.')
        return hits[0].po

    def set_matrix(self, po, what, a=None, tx=None):
        if a is not None:
            self.put(po.off + 0x10, struct.pack('>f', a), f'{what}: масштаб x {po.matrix[0]:.4g} → {a:.4g}')
        if tx is not None:
            self.put(po.off + 0x20, struct.pack('>f', tx), f'{what}: x {po.matrix[4]:.5g} → {tx:.5g}')

    def edittext_width(self, ci, xmax, what):
        ch = self.apt.chars[ci]
        if ch.type != 2:
            raise SystemExit(f'символ {ci} не EditText')
        old = f32(self.d, ch.off + 0x18)
        self.put(ch.off + 0x18, struct.pack('>f', xmax), f'EditText {ci} ({what}): ширина поля {old:.5g} → {xmax:g}')

    def align(self):
        while len(self.d) % 4:
            self.d.append(0)

    def add_place(self, owner, src_po, depth, name, tx):
        """Копия PlaceObject src_po (тот же символ и матрица) на глубине depth с именем name и x = tx — в кадр 0."""
        ch = self.apt.chars[owner]
        used = {it.po.depth for it in ch.frames[0] if it.po}
        if depth in used:
            raise SystemExit(f'символ {owner}: глубина {depth} занята')
        rec = bytearray(self.d[src_po.off:src_po.off + 0x40])
        struct.pack_into('>I', rec, 0x08, depth)
        struct.pack_into('>f', rec, 0x20, tx)
        struct.pack_into('>I', rec, 0x34, aptc.put_string(self.d, name, self.strings))
        self.align()
        po_off = len(self.d)
        self.d.extend(rec)
        self.insert_item(owner, 0, po_off, after=src_po.off)
        return po_off

    def frame_table(self, owner):
        ch = self.apt.chars[owner]
        return u32(self.d, ch.off + 0x14)

    def insert_item(self, owner, frame, item_off, after=None):
        """Новый элемент кадра (указатель item_off) — после элемента по смещению after (или в конец)."""
        ft = self.frame_table(owner)
        cnt, arr = u32(self.d, ft + 8 * frame), u32(self.d, ft + 8 * frame + 4)
        ptrs = [u32(self.d, arr + 4 * k) for k in range(cnt)]
        pos = ptrs.index(after) + 1 if after is not None else len(ptrs)
        ptrs.insert(pos, item_off)
        self.align()
        new_arr = len(self.d)
        for q in ptrs:
            self.d.extend(struct.pack('>I', q))
        self.put(ft + 8 * frame, struct.pack('>II', cnt + 1, new_arr), f'символ {owner}, кадр {frame}: элементов {cnt} → {cnt + 1}')

    def code_item(self, owner, frame, kind, sprite=None):
        """Смещение элемента Action (kind 1) или InitAction (kind 8, sprite) кадра и смещение его кода."""
        ch = self.apt.chars[owner]
        hits = [it for it in ch.frames[frame] if it.type == kind and (sprite is None or it.sprite == sprite)]
        if len(hits) != 1:
            raise SystemExit(f'символ {owner}, кадр {frame}: элементов кода {kind} — {len(hits)}')
        it = hits[0]
        return it.off, it.code

    def build(self, out_path):
        big = ph.Bigf(self.mv.big.raw)
        _, packed = self.mv.raw['0']
        big.put('0', ph.refpack_compress(bytes(self.d)) if packed else bytes(self.d))
        data = febg.build_bigf(big)
        febg.FeMovie(data)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        open(out_path, 'wb').write(data)
        return data


# ---------------------------------------------------------------- код

SPLICE = {
    # (что вставить после) — образцы команд EA и вставка (своё имя панели подставляется)
    'addItem': ([('PushValueOfVar', '{R}'), ('PushOne', None), ('PushRegister', None), ('GetNamedMember', 'EA_ZONE'),
                 ('GetNamedMember', 'gSTM'), ('CallNamedMethodPop', 'addItem')],
                '_global.EA_ZONE.gSTM.addItem({T});'),
    'refresh': ([('PushZero', None), ('PushValueOfVar', '{R}'), ('GetNamedMember', '{RC}'),
                 ('CallNamedMethodPop', 'refresh')],
                '{T}.{RC}.refresh();'),
}
SPLICE_CLASS = {
    'addItem': ([('PushRegister', 1), ('GetNamedMember', 'mcRight'), ('PushOne', None), ('PushRegister', None),
                 ('GetNamedMember', 'EA_ZONE'), ('GetNamedMember', 'gSTM'), ('CallNamedMethodPop', 'addItem')],
                '_global.EA_ZONE.gSTM.addItem(this.mcThird);'),
    'refresh': ([('PushZero', None), ('PushRegister', 1), ('GetNamedMember', 'mcRight'), ('GetNamedMember', 'rc'),
                 ('CallNamedMethodPop', 'refresh')],
                'this.mcThird.rc.refresh();'),
}


def _fill(text, sc):
    L, R, T = sc['panels']
    return text.replace('{L}', L).replace('{R}', R).replace('{T}', T).replace('{RC}', sc['rc'])


def _pattern(pat, sc):
    return [(nm, _fill(a, sc) if isinstance(a, str) else a) for nm, a in pat]


def top_functions(items):
    """{имя: индекс} функций верхнего уровня блока кадра (DefineFunction2/DefineFunction с именем)."""
    out = {}
    for i, it in enumerate(items):
        if it[0] == 'rawfn' and it[1].fname:
            if it[1].fname in out:
                raise SystemExit(f'функция {it[1].fname} определена дважды')
            out[it[1].fname] = i
    return out


def class_methods(items):
    """{метод: индекс rawfn} для «r2.Метод = function …» в InitAction класса."""
    out = {}
    for i, it in enumerate(items):
        if it[0] == 'rawfn' and not it[1].fname and i >= 2:
            prev = items[i - 1]
            if prev[0] == 'raw' and prev[1].name in ('PushConstant', 'PushWordConstant') and items[i + 1][0] == 'raw' \
                    and items[i + 1][1].name == 'SetMember':
                out[prev[1].arg] = i
    return out


def splice_in(fn_ins, kind, sc, table, notes):
    pat, src = table[kind]
    a, b = aptc.find_seq(fn_ins.body, _pattern(pat, sc))
    if a < 0:
        raise SystemExit(f'{fn_ins.fname or "метод"}: не нашёл места для вставки «{kind}»')
    a2, _ = aptc.find_seq(fn_ins.body, _pattern(pat, sc), b + 1)
    if a2 >= 0:
        raise SystemExit(f'{fn_ins.fname or "метод"}: место вставки «{kind}» не единственное')
    snippet = aptc.compile_snippet(_fill(src, sc), aptc.fn_regs(fn_ins))
    fn_ins.body[b + 1:b + 1] = snippet
    notes.append(f'  вставка после {fn_ins.body[b][1].name} «{kind}»: {_fill(src, sc)}')


def rebuild_frame_code(ed, sc, notes):
    """Блок кода кадра 0 (Action): функции EA — на месте заменить, общие — добавить, вставки — в свои места."""
    code = sc['code']
    item_off, code_off = ed.code_item(sc['owner'], 0, 1)
    items = aptc.parse_block(bytes(ed.d), code_off, ed.consts)
    funcs = top_functions(items)
    for name, src in code['replace'].items():
        if name not in funcs:
            raise SystemExit(f'{sc["rel"]}: нет функции {name}')
        new = aptc.compile_function(_fill(src, sc))
        if new[1]['name'] != name:
            raise SystemExit(f'{name}: в исходнике другое имя ({new[1]["name"]})')
        items[funcs[name]] = new
        notes.append(f'  заменена {name}')
    for name, kind in code['splice']:
        splice_in(items[funcs[name]][1], kind, sc, SPLICE, notes)
    helpers = _fill(code['helpers'], sc).strip()
    if helpers:
        add = aptc.compile_source(helpers)[:-1]          # без End
        first = 1 if items and items[0][0] == 'raw' and items[0][1].name == 'ConstantPool' else 0
        items[first:first] = add
        notes.append('  добавлены ' + ', '.join(it[1]['name'] for it in add))
    new_off = aptc.assemble(items, ed.d, ed.strings)
    ed.put(item_off + 4, struct.pack('>I', new_off), f'Action кадра 0: код @{code_off:#x} → @{new_off:#x} (пересобран)')
    return code_off, new_off


def rebuild_class_code(ed, sc, notes):
    """InitAction класса Live the Life: методы — на месте, новые — после new_after, вставки."""
    code = sc['code']
    item_off, code_off = ed.code_item(0, 0, 8, sc['class_sprite'])
    items = aptc.parse_block(bytes(ed.d), code_off, ed.consts)
    meths = class_methods(items)
    for name, src in code['methods'].items():
        if name not in meths:
            raise SystemExit(f'{sc["rel"]}: нет метода {name}')
        items[meths[name]] = aptc.compile_function(src)
        notes.append(f'  заменён метод {name}')
    for name, kind in code['splice']:
        splice_in(items[meths[name]][1], kind, sc, SPLICE_CLASS, notes)
    after = meths[code['new_after']] + 1                 # SetMember после функции
    add = aptc.compile_source(code['new'])[:-1]
    items[after + 1:after + 1] = add
    notes.append('  добавлены методы _OnUpdateThirdPanelRow, _OnHighlightThirdPanelRow')
    new_off = aptc.assemble(items, ed.d, ed.strings)
    ed.put(item_off + 8, struct.pack('>I', new_off), f'InitAction спрайта {sc["class_sprite"]}: код @{code_off:#x} → @{new_off:#x}')
    return code_off, new_off


def build_screen(sc, dst):
    src = legacy_src(sc['rel'])
    ed = Edit(src)
    notes = [f'{sc["rel"]} ({sc["what"]}):']
    L, R, T = sc['panels']
    owner = sc['owner']
    po_left, po_right = ed.place(owner, L), ed.place(owner, R)
    base_x = po_left.matrix[4]                        # 152 (у Live the Life в спрайте экрана — 1)
    ed.set_matrix(po_right, f'{R}', tx=base_x + (X_RIGHT - 152))
    ed.add_place(owner, po_right, sc['third_depth'], T, base_x + (X_THIRD - 152))
    notes.append(f'  {T}: новая панель (символ {po_right.char}) x {base_x + (X_THIRD - 152):g}, глубина {sc["third_depth"]}')
    for ci, what in sc['texts'].items():
        # поле начинается с x ряда (178 у имени, 154 у Live the Life) — ширина до края колонки минус 6
        xs = {round(it.po.matrix[4], 2) for ch in ed.apt.chars if ch.type == 5 and ch.frames
              for it in ch.frames[0] if it.po and it.po.char == ci}
        if len(xs) != 1:
            raise SystemExit(f'{sc["rel"]}: EditText {ci} стоит в {len(xs)} местах')
        x0 = xs.pop()
        ed.edittext_width(ci, float(COL_W - x0 - 6), what)
    for hs in sc['highlights']:
        ch = ed.apt.chars[hs]
        hl = [it.po for it in ch.frames[0] if it.po and it.po.name == 'mcHighlight']
        if len(hl) != 1 or abs(hl[0].matrix[0] - HL_SCALE_EA) > 1e-3:
            raise SystemExit(f'{sc["rel"]}: спрайт {hs} — нет полосы mcHighlight ×1,53')
        ed.set_matrix(hl[0], f'спрайт {hs} mcHighlight', a=HL_SCALE)
    if 'class_sprite' in sc:
        old, new = rebuild_class_code(ed, sc, notes)
    else:
        old, new = rebuild_frame_code(ed, sc, notes)
    data = ed.build(dst)
    notes += [f'  {w}' for _, _, _, w in ed.inplace]
    notes.append(f'  Apt Data {ed.orig_len} → {len(ed.d)} байт, файл {len(data)} байт')
    return notes, {'rel': sc['rel'], 'inplace': [(o, a.hex(), b.hex(), w) for o, a, b, w in ed.inplace],
                   'orig_len': ed.orig_len, 'old_code': old, 'new_code': new}


# ---------------------------------------------------------------- разбор для просмотра

def review(path, code_off, out_txt):
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    instrs = code.parse(code_off)
    with open(out_txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(feapt.Decompiler().block(instrs)) + '\n')


def cmd_build(args):
    work = opt(args, '--work', WORK)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(os.path.join(work, 'review'))
    lines, meta, built = ['draft32_legacy build: три колонки 15 + 15 + 2'], [], []
    for sc in SCREENS:
        dst = p(work, sc['rel'])
        notes, m = build_screen(sc, dst)
        lines += notes
        meta.append(m)
        built.append(sc['rel'])
        review(dst, m['new_code'], os.path.join(work, 'review', os.path.basename(sc['rel'])[:-4] + '.txt'))
    open(os.path.join(work, 'build.log'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    json.dump({'screens': meta, 'files': built}, open(os.path.join(work, 'build.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    for x in lines:
        log(x)
    if '--no-out' not in args:
        to_out = [sc['rel'] for sc in SCREENS if sc.get('out') or '--all' in args]
        old = [x.strip() for x in open(FILES, encoding='utf-8')] if os.path.exists(FILES) else []
        for rel in sorted(set(old) - set(to_out)):
            if rel and os.path.exists(p(P.out, rel)):
                log(f'  !! {rel} остался в out от прошлой сборки — убрать вручную (в Корзину)')
        for rel in to_out:
            d = p(P.out, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(p(work, rel), d)
        os.makedirs(os.path.dirname(FILES), exist_ok=True)
        with open(FILES, 'w', encoding='utf-8', newline='\n') as f:
            f.write(''.join(r + '\n' for r in to_out))
        log(f'→ {P.out}: {len(to_out)} из {len(built)} ({", ".join(os.path.basename(r) for r in to_out)}); '
            f'список — {FILES}')
    else:
        log(f'→ {work} (в out не копировалось: --no-out)')


def cmd_check(args):
    work = args[0] if args and not args[0].startswith('--') else WORK
    meta = json.load(open(os.path.join(work, 'build.json'), encoding='utf-8'))
    ok = True
    for m, sc in zip(meta['screens'], SCREENS):
        f = p(work, m['rel'])
        data = open(f, 'rb').read()
        mv = febg.FeMovie(data)
        rt = febg.build_bigf(ph.Bigf(data)) == data
        mvc, consts = feapt.load_movie(f)
        code = feapt.Code(mvc.apt.data, consts)
        nb, err = 0, []
        for t, off in feapt.code_blocks(mvc):
            try:
                code.parse(off)
                nb += 1
            except feapt.AptError as e:
                err.append(f'{t}: {e}')
        orig = febg.FeMovie.load(legacy_src(m['rel']))
        a0, a1 = orig.apt.data, mv.apt.data
        allowed = [(o, o + len(bytes.fromhex(b))) for o, _, b, _ in m['inplace']]
        diffs, k = [], 0
        while k < len(a0):
            if a0[k] != a1[k]:
                s = k
                while k < len(a0) and a0[k] != a1[k]:
                    k += 1
                diffs.append((s, k))
            k += 1
        bad = [x for x in diffs if not any(x[0] >= lo and x[1] <= hi for lo, hi in allowed)]
        other = {n: x for n, x in orig.raw.items() if n != '0'} == {n: x for n, x in mv.raw.items() if n != '0'}
        L, R, T = sc['panels']
        places = {it.po.name: it.po for it in mv.apt.chars[sc['owner']].frames[0] if it.po and it.po.name}
        panel_x = [round(places[n].matrix[4]) for n in (L, R, T) if n in places]
        good = rt and not err and not bad and other and len(panel_x) == 3 and a1[:len(a0)] is not None
        log(f'{m["rel"]}: блоков кода {nb} (разбираются{"" if not err else ", ОШИБКИ " + str(err[:2])}), '
            f'BIGF туда-обратно: {"да" if rt else "НЕТ"}; старая часть Apt Data: отличий {len(diffs)}, все в правках: '
            f'{"да" if not bad else "НЕТ " + str(bad[:3])}; прочие записи BIGF те же: {"да" if other else "НЕТ"}; '
            f'панели x {panel_x}')
        ok = ok and good
    log('ИТОГ: ' + ('всё сходится' if ok else 'ЕСТЬ ОШИБКИ'))
    if not ok:
        sys.exit(1)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    {'build': cmd_build, 'check': cmd_check}.get(cmd, lambda a: sys.exit(__doc__))(rest)


if __name__ == '__main__':
    main()
