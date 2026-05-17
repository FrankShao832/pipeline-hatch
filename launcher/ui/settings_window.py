"""Settings dialog for pipeline launcher."""

from PySide6.QtWidgets import (
    QDialog, QPushButton, QHBoxLayout, QLabel, QVBoxLayout, QFileDialog
)


class SettingsPanel(QDialog):
    """Settings dialog for configuring project paths."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        # OK and Cancel buttons
        ok_btn = QPushButton('OK', self)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton('Cancel', self)
        cancel_btn.clicked.connect(self.reject)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)

        # Project root path
        self.root_path_label = QLabel('Projects Root:')
        self.root_path_value = QLabel('None')
        label_layout = QHBoxLayout()
        label_layout.addWidget(self.root_path_label)
        label_layout.addWidget(self.root_path_value, stretch=1)
        self.root_btn = QPushButton('Browse...')

        # Publish root path
        self.publish_root_label = QLabel('Publish Root:')
        self.publish_root_value = QLabel('None')
        publish_label_layout = QHBoxLayout()
        publish_label_layout.addWidget(self.publish_root_label)
        publish_label_layout.addWidget(self.publish_root_value, stretch=1)
        self.publish_root_btn = QPushButton('Browse...')

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addLayout(label_layout)
        main_layout.addWidget(self.root_btn)
        main_layout.addLayout(publish_label_layout)
        main_layout.addWidget(self.publish_root_btn)
        main_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)
        self._connect_signals()

    def _connect_signals(self):
        """Connect button signals."""
        self.root_btn.clicked.connect(self._set_root_path)
        self.publish_root_btn.clicked.connect(self._set_publish_root_path)

    def _set_root_path(self):
        """Open file dialog to select project root directory."""
        root_path = QFileDialog.getExistingDirectory(self, "Select Projects Root")
        if root_path:
            self.root_path_value.setText(root_path)

    def _set_publish_root_path(self):
        """Open file dialog to select publish root directory."""
        publish_root_path = QFileDialog.getExistingDirectory(self, "Select Publish Root")
        if publish_root_path:
            self.publish_root_value.setText(publish_root_path)
