"""
Implements main window of the trading platform.
"""
# 导入新增的模块
import inspect
from types import ModuleType
import webbrowser
from functools import partial
from importlib import import_module
from typing import TypeVar, List, Type
from collections.abc import Callable

import vnpy
from vnpy.event import EventEngine
from vnpy.trader.gateway import BaseGateway  # 需要导入BaseGateway用于类型检查

# 保持原有的qt导入
from .qt import QtCore, QtGui, QtWidgets
from .widget import (
    BaseMonitor,
    TickMonitor,
    OrderMonitor,
    TradeMonitor,
    PositionMonitor,
    AccountMonitor,
    LogMonitor,
    ActiveOrderMonitor,
    ConnectDialog,
    ContractManager,
    TradingWidget,
    AboutDialog,
    GlobalDialog
)
from ..engine import MainEngine, BaseApp
from ..utility import get_icon_path, TRADER_DIR
from ..locale import _


WidgetType = TypeVar("WidgetType", bound="QtWidgets.QWidget")


# ========================================================================================
# 步骤 1: 创建一个新的对话框类用于添加Gateway
# ========================================================================================
class AddGatewayDialog(QtWidgets.QDialog):
    """
    用于动态添加新Gateway连接的对话框。
    """

    def __init__(self, main_engine: MainEngine, gateway_classes: list, parent=None) -> None:
        super().__init__(parent)

        self.main_engine: MainEngine = main_engine
        self.gateway_classes: list = gateway_classes
        self.gateway_name: str = ""
        self.selected_class: Type[BaseGateway] = None

        self.init_ui()

    def init_ui(self) -> None:
        """初始化UI界面"""
        self.setWindowTitle(_("添加新连接"))

        # 创建组件
        self.name_edit = QtWidgets.QLineEdit()
        self.class_combo = QtWidgets.QComboBox()
        for gateway_class in self.gateway_classes:
            # 下拉框显示类名，并将类对象本身作为数据存储
            self.class_combo.addItem(gateway_class.__name__, gateway_class)

        add_button = QtWidgets.QPushButton(_("确定"))
        add_button.clicked.connect(self.accept_setting)

        # 表单布局
        form = QtWidgets.QFormLayout()
        form.addRow(_("连接ID"), self.name_edit)
        form.addRow("Gateway", self.class_combo)
        form.addRow(add_button)

        self.setLayout(form)

    def accept_setting(self) -> None:
        """当点击确定按钮时"""
        self.gateway_name = self.name_edit.text().strip()
        self.selected_class = self.class_combo.currentData()

        # 校验输入
        if not self.gateway_name:
            QtWidgets.QMessageBox.warning(self, _("输入错误"), _("连接ID不能为空！"))
            return

        if self.gateway_name in list(self.main_engine.gateways.keys()):
            QtWidgets.QMessageBox.warning(self, _("ID冲突"), _("已存在同名连接ID，请使用其他名称！"))
            return

        self.accept()


class MainWindow(QtWidgets.QMainWindow):
    """
    Main window of the trading platform.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.window_title: str = _("VeighNa Trader 社区版 - {}   [{}]").format(vnpy.__version__, TRADER_DIR)

        self.widgets: dict[str, QtWidgets.QWidget] = {}
        self.monitors: dict[str, BaseMonitor] = {}

        # 为动态更新菜单，需要持有对系统菜单和分隔符的引用
        self.sys_menu: QtWidgets.QMenu = None
        self.sys_menu_separator: QtGui.QAction = None

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle(self.window_title)
        self.init_dock()
        self.init_toolbar()
        self.init_menu()
        self.load_window_setting("custom")

    def init_dock(self) -> None:
        """"""
        self.trading_widget, trading_dock = self.create_dock(
            TradingWidget, _("交易"), QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
        )
        tick_widget, tick_dock = self.create_dock(
            TickMonitor, _("行情"), QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        )
        order_widget, order_dock = self.create_dock(
            OrderMonitor, _("委托"), QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        )
        active_widget, active_dock = self.create_dock(
            ActiveOrderMonitor, _("活动"), QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        )
        trade_widget, trade_dock = self.create_dock(
            TradeMonitor, _("成交"), QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        )
        log_widget, log_dock = self.create_dock(
            LogMonitor, _("日志"), QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
        )
        account_widget, account_dock = self.create_dock(
            AccountMonitor, _("资金"), QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
        )
        position_widget, position_dock = self.create_dock(
            PositionMonitor, _("持仓"), QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
        )

        self.tabifyDockWidget(active_dock, order_dock)

        self.save_window_setting("default")

        tick_widget.itemDoubleClicked.connect(self.trading_widget.update_with_cell)
        position_widget.itemDoubleClicked.connect(self.trading_widget.update_with_cell)

    def init_menu(self) -> None:
        """"""
        bar: QtWidgets.QMenuBar = self.menuBar()
        bar.setNativeMenuBar(False)     # for mac and linux

        # System menu
        self.sys_menu = bar.addMenu(_("系统"))

        # 添加已有的连接
        gateway_names: list = self.main_engine.get_all_gateway_names()
        for name in gateway_names:
            self.add_gateway_menu_action(name)
        
        # 这个分隔符现在只用于分隔“连接列表”和“退出”按钮
        self.sys_menu_separator = self.sys_menu.addSeparator()

        self.add_action(
            self.sys_menu,
            _("退出"),
            get_icon_path(__file__, "exit.ico"),
            self.close
        )

        # App menu
        app_menu: QtWidgets.QMenu = bar.addMenu(_("功能"))

        all_apps: list[BaseApp] = self.main_engine.get_all_apps()
        for app in all_apps:
            ui_module: ModuleType = import_module(app.app_module + ".ui")
            widget_class: type[QtWidgets.QWidget] = getattr(ui_module, app.widget_name)

            func = partial(self.open_widget, widget_class, app.app_name)

            self.add_action(app_menu, app.display_name, app.icon_name, func, True)

        # Global setting editor
        action: QtGui.QAction = QtGui.QAction(_("配置"), self)
        action.triggered.connect(self.edit_global_setting)
        bar.addAction(action)
        
        # ========================================================================================
        # 核心改动: 将“添加连接”作为一个独立的顶级按钮添加到菜单栏
        # ========================================================================================
        add_gateway_action = self.create_action(
            _("添加连接"),
            get_icon_path(__file__, "add.ico"),
            self.open_add_gateway_dialog
        )
        bar.addAction(add_gateway_action)

        # Help menu
        help_menu: QtWidgets.QMenu = bar.addMenu(_("帮助"))

        self.add_action(
            help_menu,
            _("查询合约"),
            get_icon_path(__file__, "contract.ico"),
            partial(self.open_widget, ContractManager, "contract"),
            True
        )

        self.add_action(
            help_menu,
            _("还原窗口"),
            get_icon_path(__file__, "restore.ico"),
            self.restore_window_setting
        )

        self.add_action(
            help_menu,
            _("测试邮件"),
            get_icon_path(__file__, "email.ico"),
            self.send_test_email
        )

        self.add_action(
            help_menu,
            _("社区论坛"),
            get_icon_path(__file__, "forum.ico"),
            self.open_forum,
            True
        )

        self.add_action(
            help_menu,
            _("关于"),
            get_icon_path(__file__, "about.ico"),
            partial(self.open_widget, AboutDialog, "about"),
        )
    
    # ========================================================================================
    # 步骤 2 & 4: 实现查找、弹窗和动态添加的逻辑
    # ========================================================================================
    def find_imported_gateways_manually(self) -> List[Type[BaseGateway]]:
        """
        手动从全局作用域中查找已导入的Gateway类。
        """
        found_gateways = []
        # 注意：这里使用 __main__ 模块的全局变量，因为主运行脚本在那里
        main_module = import_module("__main__")

        for name, obj in inspect.getmembers(main_module):
            if (
                inspect.isclass(obj) and
                issubclass(obj, BaseGateway) and
                obj is not BaseGateway and
                "Gateway" in obj.__name__  # 额外的简单过滤
            ):
                found_gateways.append(obj)
        return found_gateways

    def open_add_gateway_dialog(self) -> None:
        """
        打开用于添加新Gateway的对话框
        """
        # 使用VnPy的内置方法更健壮，如果手动查找失败，可以作为备选
        # gateway_classes = self.main_engine.get_all_gateway_classes()
        gateway_classes = self.find_imported_gateways_manually()

        if not gateway_classes:
            QtWidgets.QMessageBox.information(
                self,
                _("未发现Gateway"),
                _("程序未能自动发现任何已导入的Gateway模块。\n请确保在主运行脚本中 import 了相关的Gateway类。")
            )
            return

        dialog = AddGatewayDialog(self.main_engine, gateway_classes, self)
        
        # 如果用户点击了"确定"
        if dialog.exec():
            gateway_name = dialog.gateway_name
            selected_class = dialog.selected_class
            
            # 添加Gateway到主引擎
            self.main_engine.add_gateway(selected_class, gateway_name)
            
            # 动态更新系统菜单
            self.add_gateway_menu_action(gateway_name)
            
            QtWidgets.QMessageBox.information(
                self,
                _("添加成功"),
                _("连接 {} 添加成功！\n请从“系统”菜单中点击它进行配置和连接。").format(gateway_name)
            )

    def add_gateway_menu_action(self, gateway_name: str) -> None:
        """
        在系统菜单中为指定的gateway添加一个"连接"动作。
        """
        func: Callable = partial(self.connect_gateway, gateway_name)
        action = self.create_action(
            _("连接{}").format(gateway_name),
            get_icon_path(__file__, "connect.ico"),
            func
        )
        # 将新动作插入到分隔符之前
        self.sys_menu.insertAction(self.sys_menu_separator, action)
    
    def create_action(
        self,
        action_name: str,
        icon_name: str,
        func: Callable,
    ) -> QtGui.QAction:
        """创建一个QAction"""
        icon: QtGui.QIcon = QtGui.QIcon(icon_name)
        action: QtGui.QAction = QtGui.QAction(action_name, self)
        action.triggered.connect(func)
        action.setIcon(icon)
        return action
    # ========================================================================================
    # 以下是原有的MainWindow代码，稍作调整以适应新的方法
    # ========================================================================================

    def init_toolbar(self) -> None:
        """"""
        self.toolbar: QtWidgets.QToolBar = QtWidgets.QToolBar(self)
        self.toolbar.setObjectName(_("工具栏"))
        self.toolbar.setFloatable(False)
        self.toolbar.setMovable(False)

        # Set button size
        w: int = 40
        size = QtCore.QSize(w, w)
        self.toolbar.setIconSize(size)

        # Set button spacing
        layout: QtWidgets.QLayout | None = self.toolbar.layout()
        if layout:
            layout.setSpacing(10)

        self.addToolBar(QtCore.Qt.ToolBarArea.LeftToolBarArea, self.toolbar)

    def add_action(
        self,
        menu: QtWidgets.QMenu,
        action_name: str,
        icon_name: str,
        func: Callable,
        toolbar: bool = False
    ) -> None:
        """"""
        action = self.create_action(action_name, icon_name, func)
        menu.addAction(action)
        if toolbar:
            self.toolbar.addAction(action)

    def create_dock(
        self,
        widget_class: type[WidgetType],
        name: str,
        area: QtCore.Qt.DockWidgetArea
    ) -> tuple[WidgetType, QtWidgets.QDockWidget]:
        """
        Initialize a dock widget.
        """
        widget: WidgetType = widget_class(self.main_engine, self.event_engine)      # type: ignore
        if isinstance(widget, BaseMonitor):
            self.monitors[name] = widget

        dock: QtWidgets.QDockWidget = QtWidgets.QDockWidget(name)
        dock.setWidget(widget)
        dock.setObjectName(name)
        dock.setFeatures(dock.DockWidgetFeature.DockWidgetFloatable | dock.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(area, dock)
        return widget, dock

    def connect_gateway(self, gateway_name: str) -> None:
        """
        Open connect dialog for gateway connection.
        """
        dialog: ConnectDialog = ConnectDialog(self.main_engine, gateway_name)
        dialog.exec()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """
        Call main engine close function before exit.
        """
        reply = QtWidgets.QMessageBox.question(
            self,
            _("退出"),
            _("确认退出？"),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            for widget in self.widgets.values():
                widget.close()

            for monitor in self.monitors.values():
                monitor.save_setting()

            self.save_window_setting("custom")

            self.main_engine.close()

            event.accept()
        else:
            event.ignore()

    def open_widget(self, widget_class: type[QtWidgets.QWidget], name: str) -> None:
        """
        Open contract manager.
        """
        widget: QtWidgets.QWidget | None = self.widgets.get(name, None)
        if not widget:
            widget = widget_class(self.main_engine, self.event_engine)      # type: ignore
            self.widgets[name] = widget

        if isinstance(widget, QtWidgets.QDialog):
            widget.exec()
        else:
            widget.show()

    def save_window_setting(self, name: str) -> None:
        """
        Save current window size and state by trader path and setting name.
        """
        settings: QtCore.QSettings = QtCore.QSettings(self.window_title, name)
        settings.setValue("state", self.saveState())
        settings.setValue("geometry", self.saveGeometry())

    def load_window_setting(self, name: str) -> None:
        """
        Load previous window size and state by trader path and setting name.
        """
        settings: QtCore.QSettings = QtCore.QSettings(self.window_title, name)
        state = settings.value("state")
        geometry = settings.value("geometry")

        if isinstance(state, QtCore.QByteArray):
            self.restoreState(state)
            self.restoreGeometry(geometry)

    def restore_window_setting(self) -> None:
        """
        Restore window to default setting.
        """
        self.load_window_setting("default")
        self.showMaximized()

    def send_test_email(self) -> None:
        """
        Sending a test email.
        """
        self.main_engine.send_email("VeighNa Trader", "testing", None)

    def open_forum(self) -> None:
        """
        """
        webbrowser.open("https://www.vnpy.com/forum/")

    def edit_global_setting(self) -> None:
        """
        """
        dialog: GlobalDialog = GlobalDialog()
        dialog.exec()