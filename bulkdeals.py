import nsepython
import sys
import datetime as dt
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QMessageBox, QVBoxLayout, QTableView, QAbstractItemView
from PyQt6.QtCore import QAbstractTableModel, Qt, QItemSelectionModel, QSortFilterProxyModel
from PyQt6 import uic, QtCore
import pandas as pd
import logging
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.figure as Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
logging.basicConfig(filename='app.log', level=logging.INFO)


class BulkDealsFetcher:
    def fetch(self) -> pd.DataFrame:
        try:
            return nsepython.get_bulkdeals()
        except Exception as e:
            logging.error(f"Error fetching bulk deals: {e}")
            QMessageBox.critical(
                None, "Error", f"Error fetching bulk deals: {e}")
            return pd.DataFrame()


class BulkDealsProcessor:
    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            logging.warning("No data to process")
            return df
        today_date = dt.date.today()
        if 'Quantity Traded' in df.columns and 'Trade Price / Wght. Avg. Price' in df.columns:
            df['Amt (Cr)'] = df['Quantity Traded'] * \
                df['Trade Price / Wght. Avg. Price'] / 10000000
            df = df[df['Amt (Cr)'] > 10]  # filter for >10 Crore
            df = df.groupby(['Symbol', 'Client Name'])['Amt (Cr)'].apply(
                lambda x: x[df['Buy/Sell'] == 'BUY'].sum() - x[df['Buy/Sell'] == 'SELL'].sum()).reset_index()
            df = df.rename(columns={'Amt (Cr)': 'Net Amt (Cr)'})
            df.sort_values(by=['Symbol', 'Net Amt (Cr)'], inplace=True)
        return df


class BulkDealsModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df

    def rowCount(self, index):
        return self.df.shape[0]

    def columnCount(self, index):
        return self.df.shape[1]

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if orientation == QtCore.Qt.Orientation.Horizontal:
                return self.df.columns[section]
            else:
                return str(section + 1)

    def data(self, index, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            value = self.df.iloc[index.row(), index.column()]
            return str(value)
        return None


class BulkDealsController:
    def __init__(self, ui):
        self.ui = ui
        self.fetcher = BulkDealsFetcher()
        self.processor = BulkDealsProcessor()
        self.ui.buttonFetch.clicked.connect(self.fetch_and_display)
        self.ui.buttonClear.clicked.connect(self.clear_selection)
        self.ui.buttonExit.clicked.connect(self.exit_app)
        self.selection_model = None
        self.ui.widget_layout = QVBoxLayout()
        self.ui.widget.setLayout(self.ui.widget_layout)
        self.canvas = None
        self.toolbar = None

    def exit_app(self):
        QApplication.quit()

    def clear_selection(self):

        self.ui.tableView.selectionModel().clearSelection()

    def fetch_and_display(self):
        self.df = self.fetcher.fetch()
        self.df = self.processor.process(self.df)
        model = BulkDealsModel(self.df)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(model)
        self.proxy_model.setSortRole(Qt.ItemDataRole.DisplayRole)
        self.ui.tableView.setModel(self.proxy_model)
        self.ui.tableView.horizontalHeader().sectionClicked.connect(self.on_section_clicked)
        self.ui.tableView.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ui.tableView.resizeColumnsToContents()
        self.ui.tableView.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.ui.tableView.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems)
        if self.selection_model is None:
            self.selection_model = QItemSelectionModel(
                self.ui.tableView.model())
            self.ui.tableView.setSelectionModel(self.selection_model)
        self.selection_model.selectionChanged.connect(
            self.on_selection_changed)

    def on_section_clicked(self, index):
        self.proxy_model.sort(index, Qt.SortOrder.AscendingOrder)

    def on_selection_changed(self):
        selection = self.ui.tableView.selectionModel().selectedIndexes()
        if selection:
            proxy_index = selection[0]
            source_index = self.proxy_model.mapToSource(proxy_index)
            row = source_index.row()
            column = source_index.column()
            if column == 0:  # Symbol column
                symbol = self.df.iloc[row, column]
                self.selected_df = self.df[self.df['Symbol'] == symbol]
                self.display_symbol_figure(symbol)
            elif column == 1:  # Client Name column
                client_name = self.df.iloc[row, column]
                self.selected_df = self.df[self.df['Client Name']
                                           == client_name]
                self.display_client_figure(client_name)
        else:
            self.display_message("No selection")

    def clear_layout(self):
        while self.ui.widget_layout.count():
            child = self.ui.widget_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def display_symbol_figure(self, symbol):
        self.clear_layout()
        fig, ax = plt.subplots(figsize=(6, 4))
        colors = ['g' if amount >
                  0 else 'r' for amount in self.selected_df['Net Amt (Cr)']]
        ax.barh(self.selected_df['Client Name'],
                self.selected_df['Net Amt (Cr)'], color=colors)
        ax.set_title(f"Symbol = {symbol}")
        ax.set_ylabel("Client Name")
        ax.set_xlabel("Net Amt (Cr)")
        ax.set_xlim(-max(abs(self.selected_df['Net Amt (Cr)'])),
                    max(abs(self.selected_df['Net Amt (Cr)'])))

        self.canvas = FigureCanvasQTAgg(fig)
        self.ui.widget_layout.addWidget(self.canvas)
        self.toolbar = NavigationToolbar2QT(self.canvas, self.ui.widget)
        self.ui.widget_layout.addWidget(self.toolbar)

        self.display_message("Total Net Amount : {0}".format(
            self.selected_df['Net Amt (Cr)'].sum()))

    def display_client_figure(self, client_name):
        self.clear_layout()
        fig, ax = plt.subplots(figsize=(6, 4))
        colors = ['g' if amount >
                  0 else 'r' for amount in self.selected_df['Net Amt (Cr)']]
        ax.barh(self.selected_df['Symbol'],
                self.selected_df['Net Amt (Cr)'], color=colors)
        ax.set_title(f"Client Name = {client_name}")
        ax.set_ylabel("Symbol")
        ax.set_xlabel("Net Amt (Cr)")
        ax.set_xlim(-max(abs(self.selected_df['Net Amt (Cr)'])),
                    max(abs(self.selected_df['Net Amt (Cr)'])))

        self.canvas = FigureCanvasQTAgg(fig)
        self.ui.widget_layout.addWidget(self.canvas)
        self.toolbar = NavigationToolbar2QT(self.canvas, self.ui.widget)
        self.ui.widget_layout.addWidget(self.toolbar)

        self.display_message("Total Net Amount : {0}".format(
            self.selected_df['Net Amt (Cr)'].sum()))

    def display_message(self, message):
        self.ui.label.setText(message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = uic.loadUi("fetch.ui")

    controller = BulkDealsController(ui)
    ui.show()
    sys.exit(app.exec())
